"""LLM client interface."""

from abc import ABC, abstractmethod

from agentforge.config.schemas import AgentConfig


class LLMClient(ABC):
    """Interface implemented by model clients."""

    @abstractmethod
    def generate(self, agent_config: AgentConfig, inputs: dict[str, str]) -> str:
        """Generate one agent output from its required state inputs."""
