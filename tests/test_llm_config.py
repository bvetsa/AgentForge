import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.llm import LLMConfigError, load_llm_provider_config


def test_default_llm_config_uses_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_llm_provider_config()

    assert config.provider == "mock"
    assert config.model is None
    assert config.api_key is None
    assert config.base_url is None
    assert config.timeout_seconds == 30.0


def test_project_llm_config_file_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".agentforge/config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        """
[llm]
provider = "openai-compatible"
model = "project-model"
base_url = "https://llm.example/v1"
timeout_seconds = 12.5
""".lstrip(),
        encoding="utf-8",
    )

    config = load_llm_provider_config()

    assert config.provider == "openai-compatible"
    assert config.model == "project-model"
    assert config.base_url == "https://llm.example/v1"
    assert config.timeout_seconds == 12.5


def test_llm_env_vars_override_project_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".agentforge/config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        """
[llm]
provider = "mock"
model = "project-model"
base_url = "https://project.example/v1"
timeout_seconds = 12.5
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTFORGE_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AGENTFORGE_LLM_MODEL", "env-model")
    monkeypatch.setenv("AGENTFORGE_LLM_API_KEY", "sk-env-secret")
    monkeypatch.setenv("AGENTFORGE_LLM_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("AGENTFORGE_LLM_TIMEOUT_SECONDS", "6.25")

    config = load_llm_provider_config()

    assert config.provider == "openai-compatible"
    assert config.model == "env-model"
    assert config.api_key == "sk-env-secret"
    assert config.base_url == "https://env.example/v1"
    assert config.timeout_seconds == 6.25


def test_invalid_llm_timeout_fails_clearly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTFORGE_LLM_TIMEOUT_SECONDS", "nope")

    with pytest.raises(LLMConfigError, match="must be a positive number"):
        load_llm_provider_config()


def test_api_key_is_never_written_to_project_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTFORGE_LLM_API_KEY", "sk-should-not-be-written")

    result = CliRunner().invoke(
        app,
        [
            "config",
            "set",
            "--llm-provider",
            "openai-compatible",
            "--llm-model",
            "project-model",
        ],
    )

    assert result.exit_code == 0, result.output
    config_text = (tmp_path / ".agentforge/config.toml").read_text(encoding="utf-8")
    assert "api_key" not in config_text
    assert "sk-should-not-be-written" not in config_text


def test_config_show_displays_effective_config_and_hides_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTFORGE_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AGENTFORGE_LLM_MODEL", "env-model")
    monkeypatch.setenv("AGENTFORGE_LLM_API_KEY", "sk-hidden-secret")

    result = CliRunner().invoke(app, ["config", "show"])

    assert result.exit_code == 0, result.output
    assert "provider: openai-compatible" in result.output
    assert "model: env-model" in result.output
    assert "api_key: set via AGENTFORGE_LLM_API_KEY" in result.output
    assert "sk-hidden-secret" not in result.output


def test_config_set_writes_non_secret_llm_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "config",
            "set",
            "--llm-provider",
            "openai-compatible",
            "--llm-model",
            "project-model",
            "--llm-base-url",
            "https://llm.example/v1",
            "--llm-timeout",
            "9.5",
        ],
    )

    assert result.exit_code == 0, result.output
    data = tomllib.loads((tmp_path / ".agentforge/config.toml").read_text(encoding="utf-8"))
    assert data["llm"] == {
        "provider": "openai-compatible",
        "model": "project-model",
        "base_url": "https://llm.example/v1",
        "timeout_seconds": 9.5,
    }


def test_config_set_updates_only_provided_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    initial = runner.invoke(
        app,
        [
            "config",
            "set",
            "--llm-provider",
            "openai-compatible",
            "--llm-model",
            "first-model",
            "--llm-timeout",
            "8",
        ],
    )
    update = runner.invoke(app, ["config", "set", "--llm-model", "second-model"])

    assert initial.exit_code == 0, initial.output
    assert update.exit_code == 0, update.output
    data = tomllib.loads((tmp_path / ".agentforge/config.toml").read_text(encoding="utf-8"))
    assert data["llm"]["provider"] == "openai-compatible"
    assert data["llm"]["model"] == "second-model"
    assert data["llm"]["timeout_seconds"] == 8.0


def test_config_reset_removes_project_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".agentforge/config.toml"
    config_path.parent.mkdir()
    config_path.write_text("[llm]\nprovider = \"mock\"\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["config", "reset"])

    assert result.exit_code == 0, result.output
    assert not config_path.exists()


def test_config_set_rejects_invalid_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["config", "set", "--llm-provider", "unknown"])

    assert result.exit_code == 1
    assert "Unknown LLM provider" in result.output


def test_config_set_rejects_invalid_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["config", "set", "--llm-timeout", "0"])

    assert result.exit_code == 1
    assert "--llm-timeout must be greater than 0" in result.output
