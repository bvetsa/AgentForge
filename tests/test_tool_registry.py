from typing import Any

import pytest

from agentforge.tools import Tool, ToolRegistry, ToolRegistryError


class EchoTool(Tool):
    name = "echo"
    description = "Echo input for tests."

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs


def test_tool_registry_can_register_and_retrieve_tools() -> None:
    registry = ToolRegistry()
    tool = EchoTool()

    registry.register(tool)

    assert registry.get("echo") is tool
    assert registry.names() == ["echo"]


def test_tool_registry_rejects_unknown_tools() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolRegistryError, match="Unknown tool"):
        registry.get("missing")
