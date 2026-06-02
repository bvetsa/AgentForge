from pathlib import Path

import pytest

from agentforge.config.loader import ConfigLoadError, load_agent_config, load_workflow_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_valid_agent_config() -> None:
    config = load_agent_config(PROJECT_ROOT / "examples/agents/planner.yaml")

    assert config.name == "planner"
    assert config.input_keys == ["user_request"]
    assert config.output_key == "plan"


def test_load_valid_workflow_config() -> None:
    config = load_workflow_config(PROJECT_ROOT / "examples/workflows/basic_feature.yaml")

    assert config.name == "basic_feature"
    assert config.agents == [
        "examples/agents/planner.yaml",
        "examples/agents/frontend.yaml",
        "examples/agents/backend.yaml",
        "examples/agents/testing.yaml",
        "examples/agents/reviewer.yaml",
    ]


def test_invalid_yaml_raises_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("name: [", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="Invalid YAML"):
        load_agent_config(config_path)


def test_invalid_agent_config_raises_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid-agent.yaml"
    config_path.write_text("name: incomplete\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="Invalid agent config"):
        load_agent_config(config_path)
