import json
from pathlib import Path

from typer.testing import CliRunner

from agentforge.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_run_command_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(PROJECT_ROOT / "examples/workflows/basic_feature.yaml"),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
    )

    assert result.exit_code == 0
    assert "completed successfully" in result.stdout
    run_directories = list((tmp_path / ".agentforge/runs").iterdir())
    assert len(run_directories) == 1
    tool_calls = json.loads((run_directories[0] / "tool_calls.json").read_text(encoding="utf-8"))
    assert tool_calls
    llm_calls = json.loads((run_directories[0] / "llm_calls.json").read_text(encoding="utf-8"))
    assert all(call["provider"] == "mock" for call in llm_calls)
    assert all(call["model"] == "mock-deterministic-v1" for call in llm_calls)


def test_cli_run_command_records_tool_calls_for_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(PROJECT_ROOT / "examples/workflows/basic_feature.yaml"),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--project-root",
            str(PROJECT_ROOT / "examples/sample_project"),
        ],
    )

    assert result.exit_code == 0
    run_directories = list((tmp_path / ".agentforge/runs").iterdir())
    assert len(run_directories) == 1
    tool_calls = json.loads((run_directories[0] / "tool_calls.json").read_text(encoding="utf-8"))
    assert any(
        record["tool"] == "list_files" and "src/app.py" in record["output_preview"]
        for record in tool_calls
    )


def test_cli_run_command_no_project_context_writes_empty_tool_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(PROJECT_ROOT / "examples/workflows/basic_feature.yaml"),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--no-project-context",
        ],
    )

    assert result.exit_code == 0
    run_directories = list((tmp_path / ".agentforge/runs").iterdir())
    assert len(run_directories) == 1
    tool_calls = json.loads((run_directories[0] / "tool_calls.json").read_text(encoding="utf-8"))
    assert tool_calls == []


def test_cli_run_command_rejects_project_root_with_no_project_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(PROJECT_ROOT / "examples/workflows/basic_feature.yaml"),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--project-root",
            str(PROJECT_ROOT / "examples/sample_project"),
            "--no-project-context",
        ],
    )

    assert result.exit_code == 1
    assert "--project-root and --no-project-context cannot be used together" in result.stderr
