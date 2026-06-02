"""Load and validate AgentForge YAML configuration files."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentforge.config.schemas import AgentConfig, WorkflowConfig


class ConfigLoadError(ValueError):
    """Raised when a configuration file cannot be loaded or validated."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigLoadError(f"Configuration file not found: {path}") from error
    except OSError as error:
        raise ConfigLoadError(f"Could not read configuration file {path}: {error}") from error

    try:
        data = yaml.safe_load(contents)
    except yaml.YAMLError as error:
        raise ConfigLoadError(f"Invalid YAML in {path}: {error}") from error

    if not isinstance(data, dict):
        raise ConfigLoadError(f"Configuration file must contain a YAML mapping: {path}")

    return data


def load_agent_config(path: str | Path) -> AgentConfig:
    """Load and validate an agent configuration file."""
    config_path = Path(path)
    try:
        return AgentConfig.model_validate(_load_yaml(config_path))
    except ValidationError as error:
        raise ConfigLoadError(f"Invalid agent config in {config_path}: {error}") from error


def load_workflow_config(path: str | Path) -> WorkflowConfig:
    """Load and validate a workflow configuration file."""
    config_path = Path(path)
    try:
        return WorkflowConfig.model_validate(_load_yaml(config_path))
    except ValidationError as error:
        raise ConfigLoadError(f"Invalid workflow config in {config_path}: {error}") from error


def resolve_agent_path(workflow_path: str | Path, agent_path: str) -> Path:
    """Resolve agent paths from either the workflow directory or the current directory."""
    configured_path = Path(agent_path)
    if configured_path.is_absolute():
        return configured_path

    workflow_relative_path = Path(workflow_path).parent / configured_path
    if workflow_relative_path.exists():
        return workflow_relative_path

    for parent in Path(workflow_path).resolve().parents:
        parent_relative_path = parent / configured_path
        if parent_relative_path.exists():
            return parent_relative_path

    return configured_path
