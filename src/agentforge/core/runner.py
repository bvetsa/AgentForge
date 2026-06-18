"""Sequential workflow runner."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentforge.core.artifacts import ArtifactWriter
from agentforge.core.state import MissingStateInputError, WorkflowState
from agentforge.core.trace import LLMCallLog, ToolCallLog, TraceLog
from agentforge.core.workflow import Workflow
from agentforge.llm import AgentPromptBuilder, LLMClient, LLMProvider, MockLLMProvider
from agentforge.patches import DeterministicPatchGenerator, PatchGenerator, PatchProposal
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
    llm_calls: list[dict[str, object]]
    patch_proposals: list[dict[str, object]]
    run_directory: Path


class WorkflowRunner:
    """Execute configured agents in order with shared state."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        llm_client: LLMClient | None = None,
        prompt_builder: AgentPromptBuilder | None = None,
        patch_generator: PatchGenerator | None = None,
        runs_directory: str | Path = ".agentforge/runs",
    ) -> None:
        if llm_provider is not None and llm_client is not None:
            raise ValueError("Pass either llm_provider or llm_client, not both.")
        self.llm_provider = llm_provider or llm_client or MockLLMProvider()
        self.prompt_builder = prompt_builder or AgentPromptBuilder()
        self.patch_generator = patch_generator or DeterministicPatchGenerator()
        self.artifact_writer = ArtifactWriter(runs_directory)

    def run(
        self,
        workflow_path: str | Path,
        input_text: str,
        project_root: str | Path | None = None,
        use_project_context: bool = True,
        stop_before_agent_names: set[str] | None = None,
        run_id: str | None = None,
        patch_id_prefix: str = "",
        merge_patch_manifest: bool = False,
    ) -> RunResult:
        """Run a workflow and persist its artifacts."""
        workflow = Workflow.from_file(workflow_path)
        run_id = run_id or self._create_run_id()
        state = WorkflowState.from_user_request(input_text)
        trace_log = TraceLog()
        tool_registry = self._create_tool_registry(project_root, use_project_context)
        tool_call_log = ToolCallLog()
        llm_call_log = LLMCallLog()
        agent_outputs: list[tuple[str, str]] = []
        patch_proposals: list[PatchProposal] = []
        stop_names = stop_before_agent_names or set()

        for agent in workflow.agents:
            if agent.config.name in stop_names:
                break
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
                invocation = self.prompt_builder.build(agent.config, inputs)
                response = self.llm_provider.generate(invocation)
                llm_call_log.append(invocation, response)
                output = response.content
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
                    llm_call_log,
                    patch_proposals,
                    merge_patch_manifest=merge_patch_manifest,
                )
                raise WorkflowExecutionError(
                    f"Workflow '{workflow.config.name}' failed: {error}. "
                    f"Artifacts written to {run_directory}",
                    run_directory=run_directory,
                ) from error

            state.set_output(agent.config.output_key, output)
            agent_outputs.append((agent.config.name, output))
            if agent.config.produces_patches:
                proposal = self.patch_generator.create(
                    agent.config,
                    sequence=len(patch_proposals) + 1,
                )
                if patch_id_prefix:
                    proposal = _prefix_patch_proposal(proposal, patch_id_prefix)
                patch_proposals.append(proposal)
            trace_log.append_success(agent.config)

        run_directory = self._write_artifacts(
            run_id,
            workflow,
            input_text,
            state,
            trace_log,
            agent_outputs,
            tool_call_log,
            llm_call_log,
            patch_proposals,
            merge_patch_manifest=merge_patch_manifest,
        )
        return RunResult(
            run_id=run_id,
            workflow_name=workflow.config.name,
            state=state.to_dict(),
            trace_events=trace_log.to_list(),
            tool_calls=tool_call_log.to_list(),
            llm_calls=llm_call_log.to_list(),
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
        llm_call_log: LLMCallLog,
        patch_proposals: list[PatchProposal],
        merge_patch_manifest: bool = False,
    ) -> Path:
        return self.artifact_writer.write(
            run_id=run_id,
            workflow_name=workflow.config.name,
            input_text=input_text,
            state=state.to_dict(),
            trace_events=trace_log.to_list(),
            agent_outputs=agent_outputs,
            tool_calls=tool_call_log.to_list(),
            llm_calls=llm_call_log.to_list(),
            patch_proposals=patch_proposals,
            merge_patch_manifest=merge_patch_manifest,
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


def _prefix_patch_proposal(proposal: PatchProposal, prefix: str) -> PatchProposal:
    patch_id = f"{prefix}{proposal.id}"
    return proposal.model_copy(
        update={
            "id": patch_id,
            "patch_file": f"patches/{patch_id}.diff",
        }
    )
