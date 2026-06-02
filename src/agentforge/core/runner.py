"""Sequential workflow runner."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentforge.core.artifacts import ArtifactWriter
from agentforge.core.state import MissingStateInputError, WorkflowState
from agentforge.core.trace import TraceLog
from agentforge.core.workflow import Workflow
from agentforge.llm.base import LLMClient
from agentforge.llm.mock import MockLLMClient


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

    def run(self, workflow_path: str | Path, input_text: str) -> RunResult:
        """Run a workflow and persist its artifacts."""
        workflow = Workflow.from_file(workflow_path)
        run_id = self._create_run_id()
        state = WorkflowState.from_user_request(input_text)
        trace_log = TraceLog()
        agent_outputs: list[tuple[str, str]] = []

        for agent in workflow.agents:
            try:
                inputs = agent.collect_inputs(state)
                output = self.llm_client.generate(agent.config, inputs)
            except MissingStateInputError as error:
                trace_log.append_failure(agent.config, str(error))
                run_directory = self._write_artifacts(
                    run_id, workflow, input_text, state, trace_log, agent_outputs
                )
                raise WorkflowExecutionError(
                    f"Workflow '{workflow.config.name}' failed: {error}. "
                    f"Artifacts written to {run_directory}",
                    run_directory=run_directory,
                ) from error

            state.set_output(agent.config.output_key, output)
            agent_outputs.append((agent.config.name, output))
            trace_log.append_success(agent.config)

        run_directory = self._write_artifacts(
            run_id, workflow, input_text, state, trace_log, agent_outputs
        )
        return RunResult(
            run_id=run_id,
            workflow_name=workflow.config.name,
            state=state.to_dict(),
            trace_events=trace_log.to_list(),
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
    ) -> Path:
        return self.artifact_writer.write(
            run_id=run_id,
            workflow_name=workflow.config.name,
            input_text=input_text,
            state=state.to_dict(),
            trace_events=trace_log.to_list(),
            agent_outputs=agent_outputs,
        )

    @staticmethod
    def _create_run_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid4().hex[:8]}"
