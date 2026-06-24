"""Project and environment configuration for LLM providers."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from agentforge.llm.base import LLMError

CONFIG_RELATIVE_PATH = Path(".agentforge/config.toml")
SUPPORTED_LLM_PROVIDERS = {"mock", "openai-compatible"}

ENV_LLM_PROVIDER = "AGENTFORGE_LLM_PROVIDER"
ENV_LLM_MODEL = "AGENTFORGE_LLM_MODEL"
ENV_LLM_API_KEY = "AGENTFORGE_LLM_API_KEY"
ENV_LLM_BASE_URL = "AGENTFORGE_LLM_BASE_URL"
ENV_LLM_TIMEOUT_SECONDS = "AGENTFORGE_LLM_TIMEOUT_SECONDS"
LLM_ENVIRONMENT_VARIABLES = (
    ENV_LLM_PROVIDER,
    ENV_LLM_MODEL,
    ENV_LLM_API_KEY,
    ENV_LLM_BASE_URL,
    ENV_LLM_TIMEOUT_SECONDS,
)


class LLMConfigError(LLMError):
    """Raised when LLM provider configuration is invalid."""


@dataclass(frozen=True)
class LLMProviderConfig:
    """Effective provider configuration after applying all sources."""

    provider: str = "mock"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0


def load_llm_provider_config(
    project_root: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> LLMProviderConfig:
    """Load effective LLM config using env vars, project config, then defaults."""
    env = os.environ if env is None else env
    config = LLMProviderConfig()
    config_path = get_project_config_path(project_root)

    if config_path.exists():
        config = _merge_config(config, _read_project_llm_config(config_path))

    config = _merge_config(config, _read_environment_llm_config(env))
    return _validate_config(config)


def get_project_config_path(project_root: str | Path | None = None) -> Path:
    """Return the project-local AgentForge config path."""
    root = Path.cwd() if project_root is None else Path(project_root)
    return root / CONFIG_RELATIVE_PATH


def set_project_llm_config(
    updates: Mapping[str, object],
    project_root: str | Path | None = None,
) -> Path:
    """Update project-local non-secret LLM settings and return the config path."""
    config_path = get_project_config_path(project_root)
    data = _read_project_config_document(config_path) if config_path.exists() else {}
    llm_data = data.get("llm", {})
    if not isinstance(llm_data, dict):
        raise LLMConfigError("Invalid .agentforge/config.toml: [llm] must be a table.")

    normalized_updates = _normalize_file_updates(updates)
    llm_data = dict(llm_data)
    llm_data.pop("api_key", None)
    llm_data.update(normalized_updates)
    data["llm"] = llm_data

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_dump_toml(data), encoding="utf-8")
    return config_path


def reset_project_llm_config(project_root: str | Path | None = None) -> bool:
    """Remove the project-local AgentForge config file if it exists."""
    config_path = get_project_config_path(project_root)
    if not config_path.exists():
        return False
    config_path.unlink()
    return True


def parse_timeout_seconds(value: object, *, source: str) -> float:
    """Parse and validate a positive timeout value."""
    if isinstance(value, bool):
        raise LLMConfigError(f"{source} must be a positive number.")
    try:
        timeout_seconds = float(value)
    except (TypeError, ValueError) as error:
        raise LLMConfigError(f"{source} must be a positive number.") from error
    if timeout_seconds <= 0:
        raise LLMConfigError(f"{source} must be greater than 0.")
    return timeout_seconds


def validate_provider_name(provider: str, *, source: str) -> str:
    """Normalize and validate a supported provider name."""
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_LLM_PROVIDERS:
        valid = ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
        raise LLMConfigError(
            f"Unknown LLM provider {provider!r} from {source}. Supported providers: {valid}."
        )
    return normalized


def non_secret_config_dict(config: LLMProviderConfig) -> dict[str, object]:
    """Return display-safe effective config values."""
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "timeout_seconds": config.timeout_seconds,
        "api_key": "set via AGENTFORGE_LLM_API_KEY" if config.api_key else "not set",
    }


def _merge_config(
    config: LLMProviderConfig,
    values: Mapping[str, object],
) -> LLMProviderConfig:
    merged = config
    for key, value in values.items():
        merged = replace(merged, **{key: value})
    return merged


def _read_project_llm_config(config_path: Path) -> dict[str, object]:
    data = _read_project_config_document(config_path)
    llm_data = data.get("llm", {})
    if not isinstance(llm_data, dict):
        raise LLMConfigError("Invalid .agentforge/config.toml: [llm] must be a table.")
    if "api_key" in llm_data:
        raise LLMConfigError(
            "Invalid .agentforge/config.toml: api_key is not allowed. "
            "Use AGENTFORGE_LLM_API_KEY instead."
        )
    return _normalize_file_updates(llm_data)


def _read_project_config_document(config_path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise LLMConfigError(f"Invalid TOML in {config_path}: {error}") from error
    if not isinstance(data, dict):
        raise LLMConfigError(f"Invalid TOML in {config_path}: root must be a table.")
    return data


def _read_environment_llm_config(env: Mapping[str, str]) -> dict[str, object]:
    values: dict[str, object] = {}
    if ENV_LLM_PROVIDER in env:
        values["provider"] = env[ENV_LLM_PROVIDER]
    if ENV_LLM_MODEL in env:
        values["model"] = _optional_string(env[ENV_LLM_MODEL])
    if ENV_LLM_API_KEY in env:
        values["api_key"] = _optional_string(env[ENV_LLM_API_KEY])
    if ENV_LLM_BASE_URL in env:
        values["base_url"] = _optional_string(env[ENV_LLM_BASE_URL])
    if ENV_LLM_TIMEOUT_SECONDS in env:
        values["timeout_seconds"] = parse_timeout_seconds(
            env[ENV_LLM_TIMEOUT_SECONDS],
            source=ENV_LLM_TIMEOUT_SECONDS,
        )
    return values


def _normalize_file_updates(updates: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in updates.items():
        if key == "provider":
            if not isinstance(value, str):
                raise LLMConfigError("llm.provider must be a string.")
            normalized["provider"] = value
        elif key == "model":
            normalized["model"] = _normalize_optional_file_string(value, "llm.model")
        elif key == "base_url":
            normalized["base_url"] = _normalize_optional_file_string(value, "llm.base_url")
        elif key == "timeout_seconds":
            normalized["timeout_seconds"] = parse_timeout_seconds(
                value,
                source="llm.timeout_seconds",
            )
        elif key == "api_key":
            continue
        else:
            raise LLMConfigError(f"Unknown LLM config key: {key}.")
    return normalized


def _validate_config(config: LLMProviderConfig) -> LLMProviderConfig:
    provider = validate_provider_name(config.provider, source="effective config")
    timeout_seconds = parse_timeout_seconds(
        config.timeout_seconds,
        source="llm.timeout_seconds",
    )
    return LLMProviderConfig(
        provider=provider,
        model=_normalize_optional_file_string(config.model, "llm.model"),
        api_key=_normalize_optional_file_string(config.api_key, "AGENTFORGE_LLM_API_KEY"),
        base_url=_normalize_optional_file_string(config.base_url, "llm.base_url"),
        timeout_seconds=timeout_seconds,
    )


def _normalize_optional_file_string(value: object, source: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LLMConfigError(f"{source} must be a string.")
    return _optional_string(value)


def _optional_string(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _dump_toml(data: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for section_name, section_value in data.items():
        if not isinstance(section_value, Mapping):
            raise LLMConfigError(f"Cannot write non-table config value: {section_name}.")
        if lines:
            lines.append("")
        lines.append(f"[{section_name}]")
        for key, value in section_value.items():
            if value is None:
                continue
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    raise LLMConfigError(f"Cannot write unsupported TOML value: {value!r}.")


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
