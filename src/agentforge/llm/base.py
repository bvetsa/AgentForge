"""LLM provider interface and data contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentInvocation:
    """Provider-ready request for one agent text generation step."""

    agent_name: str
    description: str
    system_prompt: str
    input_keys: list[str]
    output_key: str
    inputs: dict[str, str]
    prompt: str


@dataclass(frozen=True)
class AgentResponse:
    """Provider response for one agent text generation step."""

    content: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)
    patch_proposals: list[dict[str, Any]] = field(default_factory=list)
    tool_requests: list[dict[str, Any]] = field(default_factory=list)
    decisions: dict[str, Any] | None = None


class LLMProvider(ABC):
    """Interface implemented by text generation providers."""

    @abstractmethod
    def generate(self, invocation: AgentInvocation) -> AgentResponse:
        """Generate one agent response from a provider-ready invocation."""


LLMClient = LLMProvider
