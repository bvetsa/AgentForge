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
    assert len(list((tmp_path / ".agentforge/runs").iterdir())) == 1
