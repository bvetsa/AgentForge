"""Deterministic mock LLM client for the MVP."""

from agentforge.config.schemas import AgentConfig
from agentforge.llm.base import LLMClient


class MockLLMClient(LLMClient):
    """Return predictable text so the workflow engine can be tested locally."""

    def generate(self, agent_config: AgentConfig, inputs: dict[str, str]) -> str:
        input_summary = "\n".join(f"- {key}: {value}" for key, value in inputs.items())
        return f"Mock output from {agent_config.name}\n\nInputs:\n{input_summary}"
