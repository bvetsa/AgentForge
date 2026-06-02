"""Agent representation used by the workflow runner."""

from dataclasses import dataclass

from agentforge.config.schemas import AgentConfig
from agentforge.core.state import WorkflowState


@dataclass(frozen=True)
class Agent:
    """A configured specialist role in a workflow."""

    config: AgentConfig

    def collect_inputs(self, state: WorkflowState) -> dict[str, str]:
        """Read this agent's required inputs from shared workflow state."""
        return state.get_required_inputs(self.config.input_keys)
