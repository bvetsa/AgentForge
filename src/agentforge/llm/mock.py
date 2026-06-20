"""Deterministic mock LLM provider for offline runs and tests."""

from agentforge.llm.base import AgentInvocation, AgentResponse, LLMProvider


class MockLLMProvider(LLMProvider):
    """Return predictable text so the workflow engine can be tested locally."""

    provider_name = "mock"
    model_name = "mock-deterministic-v1"

    def generate(self, invocation: AgentInvocation) -> AgentResponse:
        input_summary = "\n".join(
            f"- {key}: {value}" for key, value in invocation.inputs.items()
        )
        return AgentResponse(
            content=f"Mock output from {invocation.agent_name}\n\nInputs:\n{input_summary}",
            provider=self.provider_name,
            model=self.model_name,
            metadata={"deterministic": True, "offline": True},
        )


MockLLMClient = MockLLMProvider
