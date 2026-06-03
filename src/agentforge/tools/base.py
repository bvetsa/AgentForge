"""Base classes for AgentForge tools."""

from abc import ABC, abstractmethod
from typing import Any


class ToolError(ValueError):
    """Raised when a tool cannot safely complete a request."""


class Tool(ABC):
    """A controlled capability that can be exposed to an agent."""

    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the tool with validated keyword arguments."""
