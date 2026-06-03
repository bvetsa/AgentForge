"""Tool registry for controlled agent capabilities."""

from agentforge.tools.base import Tool


class ToolRegistryError(ValueError):
    """Raised when a tool registry operation cannot be completed."""


class ToolRegistry:
    """Register and retrieve tools by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Add a tool to the registry."""
        if tool.name in self._tools:
            raise ToolRegistryError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Return a registered tool by name."""
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolRegistryError(f"Unknown tool: {name}") from error

    def names(self) -> list[str]:
        """Return registered tool names in sorted order."""
        return sorted(self._tools)
