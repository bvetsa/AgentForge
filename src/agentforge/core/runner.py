"""Sequential workflow runner."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentforge.core.artifacts import ArtifactWriter
from agentforge.core.state import MissingStateInputError, WorkflowState
from agentforge.core.trace import ToolCallLog, TraceLog
from agentforge.core.workflow import Workflow
from agentforge.llm.base import LLMClient
from agentforge.llm.mock import MockLLMClient
from agentforge.patches import PatchProposal, create_mock_patch_proposal
from agentforge.tools import (
    ToolError,
    ToolRegistry,
    ToolRegistryError,
    create_filesystem_tool_registry,
)


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow cannot complete."""

    def __init__(self, message: str, run_directory: Path | None = None) -> None:
        super().__init__(message)
        self.run_directory = run_directory


@dataclass(frozen=True)
class RunResult:
    """Result returned after a successful workflow run."""

    run_id: str
    workflow_name: str
    state: dict[str, str]
    trace_events: list[dict[str, object]]
    tool_calls: list[dict[str, object]]
    patch_proposals: list[dict[str, object]]
    run_directory: Path


class WorkflowRunner:
    """Execute configured agents in order with shared state."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        runs_directory: str | Path = ".agentforge/runs",
    ) -> None:
        self.llm_client = llm_client or MockLLMClient()
        self.artifact_writer = ArtifactWriter(runs_directory)

    def run(
        self,
        workflow_path: str | Path,
        input_text: str,
        project_root: str | Path | None = None,
        use_project_context: bool = True,
    ) -> RunResult:
        """Run a workflow and persist its artifacts."""
        workflow = Workflow.from_file(workflow_path)
        run_id = self._create_run_id()
        state = WorkflowState.from_user_request(input_text)
        trace_log = TraceLog()
        tool_registry = self._create_tool_registry(project_root, use_project_context)
        tool_call_log = ToolCallLog()
        agent_outputs: list[tuple[str, str]] = []
        patch_proposals: list[PatchProposal] = []

        for agent in workflow.agents:
            try:
                inputs = agent.collect_inputs(state)
                if tool_registry is not None:
                    inputs["tool_context"] = self._collect_tool_context(
                        agent_name=agent.config.name,
                        allowed_tools=agent.config.allowed_tools,
                        inputs=inputs,
                        tool_registry=tool_registry,
                        tool_call_log=tool_call_log,
                    )
                output = self.llm_client.generate(agent.config, inputs)
            except MissingStateInputError as error:
                trace_log.append_failure(agent.config, str(error))
                run_directory = self._write_artifacts(
                    run_id,
                    workflow,
                    input_text,
                    state,
                    trace_log,
                    agent_outputs,
                    tool_call_log,
                    patch_proposals,
                )
                raise WorkflowExecutionError(
                    f"Workflow '{workflow.config.name}' failed: {error}. "
                    f"Artifacts written to {run_directory}",
                    run_directory=run_directory,
                ) from error

            state.set_output(agent.config.output_key, output)
            agent_outputs.append((agent.config.name, output))
            if agent.config.produces_patches:
                patch_proposals.append(
                    create_mock_patch_proposal(
                        agent.config,
                        sequence=len(patch_proposals) + 1,
                    )
                )
            trace_log.append_success(agent.config)

        run_directory = self._write_artifacts(
            run_id,
            workflow,
            input_text,
            state,
            trace_log,
            agent_outputs,
            tool_call_log,
            patch_proposals,
        )
        return RunResult(
            run_id=run_id,
            workflow_name=workflow.config.name,
            state=state.to_dict(),
            trace_events=trace_log.to_list(),
            tool_calls=tool_call_log.to_list(),
            patch_proposals=[proposal.model_dump() for proposal in patch_proposals],
            run_directory=run_directory,
        )

    def _write_artifacts(
        self,
        run_id: str,
        workflow: Workflow,
        input_text: str,
        state: WorkflowState,
        trace_log: TraceLog,
        agent_outputs: list[tuple[str, str]],
        tool_call_log: ToolCallLog,
        patch_proposals: list[PatchProposal],
    ) -> Path:
        return self.artifact_writer.write(
            run_id=run_id,
            workflow_name=workflow.config.name,
            input_text=input_text,
            state=state.to_dict(),
            trace_events=trace_log.to_list(),
            agent_outputs=agent_outputs,
            tool_calls=tool_call_log.to_list(),
            patch_proposals=patch_proposals,
        )

    @staticmethod
    def _create_tool_registry(
        project_root: str | Path | None,
        use_project_context: bool,
    ) -> ToolRegistry | None:
        if not use_project_context:
            return None
        root = Path.cwd() if project_root is None else project_root
        try:
            return create_filesystem_tool_registry(root)
        except ToolError as error:
            raise WorkflowExecutionError(f"Could not initialize tools: {error}") from error

    def _collect_tool_context(
        self,
        *,
        agent_name: str,
        allowed_tools: list[str],
        inputs: dict[str, str],
        tool_registry: ToolRegistry,
        tool_call_log: ToolCallLog,
    ) -> str:
        if not allowed_tools:
            return "No allowed tools configured."

        sections: list[str] = []
        for tool_name in allowed_tools:
            tool_input = self._default_tool_input(tool_name, inputs)
            try:
                tool = tool_registry.get(tool_name)
                output = tool.run(**tool_input)
            except (ToolError, ToolRegistryError) as error:
                tool_call_log.append_failure(
                    agent_name=agent_name,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    error_message=str(error),
                )
                sections.append(f"## {tool_name}\nERROR: {error}")
                continue

            tool_call_log.append_success(
                agent_name=agent_name,
                tool_name=tool_name,
                tool_input=tool_input,
                output=output,
            )
            sections.append(f"## {tool_name}\n{self._format_tool_output(output)}")

        return "\n\n".join(sections)

    @staticmethod
    def _default_tool_input(tool_name: str, inputs: dict[str, str]) -> dict[str, Any]:
        if tool_name == "search_files":
            return {"query": inputs.get("user_request", "")}
        if tool_name == "read_file":
            return {"path": "README.md"}
        return {}

    @staticmethod
    def _format_tool_output(output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, list) and all(isinstance(item, str) for item in output):
            return "\n".join(output)
        return json.dumps(output, indent=2, sort_keys=True)

    @staticmethod
    def _create_run_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid4().hex[:8]}"
