import json
import os
from pathlib import Path

from typer.testing import CliRunner

from agentforge.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dev_run_creates_run_directory_and_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    run_directory = single_run_directory(tmp_path)
    assert (run_directory / "dev_run_summary.json").exists()


def test_dev_run_defaults_project_root_to_current_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = create_detectable_project(tmp_path)
    monkeypatch.chdir(project_root)

    result = CliRunner().invoke(
        app,
        ["dev", "run", "--input", "Add a todo endpoint to a FastAPI app"],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    summary = read_summary(single_run_directory(project_root))
    assert summary["project_root"] == str(project_root.resolve())


def test_dev_run_requires_input(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["dev", "run"])

    assert result.exit_code != 0
    assert "Missing option" in result.output
    assert not (tmp_path / ".agentforge/runs").exists()


def test_dev_run_no_does_not_apply_patches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_detectable_project(tmp_path)
    before = snapshot_project(project_root)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert snapshot_project(project_root) == before
    manifest = read_manifest(single_run_directory(tmp_path))
    assert {entry["status"] for entry in manifest} == {"proposed"}


def test_dev_run_no_does_not_run_tests(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    run_directory = single_run_directory(tmp_path)
    assert not (run_directory / "test_results.json").exists()
    assert not (run_directory / "test_output.txt").exists()


def test_dev_run_yes_applies_all_proposed_patches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    add_venv_to_path(monkeypatch)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = read_manifest(single_run_directory(tmp_path))
    assert [entry["status"] for entry in manifest] == ["applied", "applied", "applied"]
    for entry in manifest:
        target_path = project_root / entry["target_file"]
        assert target_path.exists()
        assert entry["title"] in target_path.read_text(encoding="utf-8")


def test_dev_run_yes_runs_tests_after_applying_patches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    add_venv_to_path(monkeypatch)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Applying patches..." in result.output
    assert "Running tests..." in result.output
    assert "[ok] Tests passed" in result.output
    summary = read_summary(single_run_directory(tmp_path))
    assert summary["test_status"] == "passed"


def test_dev_run_writes_test_results_into_same_run_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    add_venv_to_path(monkeypatch)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    run_directory = single_run_directory(tmp_path)
    assert (run_directory / "test_results.json").exists()
    assert (run_directory / "test_output.txt").exists()
    assert not (tmp_path / ".agentforge/test-runs").exists()


def test_dev_run_summary_records_pipeline_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    add_venv_to_path(monkeypatch)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    summary = read_summary(single_run_directory(tmp_path))
    assert summary["user_request"] == "Add a todo endpoint to a FastAPI app"
    assert summary["project_root"] == str(project_root.resolve())
    assert summary["workflow_path"].endswith("examples/workflows/basic_feature.yaml")
    assert summary["status"] == "tests_passed"
    assert len(summary["generated_patches"]) == 3
    assert len(summary["applied_patches"]) == 3
    assert summary["test_status"] == "passed"
    assert summary["planner_decisions"][0]["next_action"] == "send_to_reviewer"
    assert summary["final_verdict"] == "Changes applied successfully and tests passed."
    assert summary["cycles"][0]["approval"] == "approved"
    assert summary["cycles"][0]["selected_agents"] == ["frontend", "backend", "testing"]


def test_dev_run_default_approval_is_no(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_detectable_project(tmp_path)
    before = snapshot_project(project_root)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
        input="\n",
    )

    assert result.exit_code == 0, result.output
    assert snapshot_project(project_root) == before
    summary = read_summary(single_run_directory(tmp_path))
    assert summary["status"] == "not_applied"
    assert summary["test_status"] == "not_run"
    assert summary["cycles"][0]["approval"] == "declined"


def test_dev_run_does_not_call_reviewer_before_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    run_directory = single_run_directory(tmp_path)
    trace = json.loads((run_directory / "trace.json").read_text(encoding="utf-8"))
    assert [event["agent"] for event in trace] == [
        "planner",
        "frontend",
        "backend",
        "testing",
    ]
    state = json.loads((run_directory / "state.json").read_text(encoding="utf-8"))
    assert "review" not in state


def test_dev_run_final_verdict_is_printed_after_planner_decision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    add_venv_to_path(monkeypatch)
    project_root = create_detectable_project(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output.index("Planner decision:") < result.output.index("Final verdict:")
    assert "Apply all proposed patches?" not in result.output


def test_dev_run_workflow_override_works(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_detectable_project(tmp_path)
    workflow_path = write_custom_workflow(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "dev",
            "run",
            "--project-root",
            str(project_root),
            "--workflow",
            str(workflow_path),
            "--input",
            "Add a todo endpoint to a FastAPI app",
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    summary = read_summary(single_run_directory(tmp_path))
    assert summary["workflow_path"] == str(workflow_path.resolve())
    assert [patch["agent_name"] for patch in summary["generated_patches"]] == ["backend"]


def create_detectable_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        "Run `python -m pytest --version` before shipping.\n",
        encoding="utf-8",
    )
    return project_root


def write_custom_workflow(tmp_path: Path) -> Path:
    planner_path = tmp_path / "planner.yaml"
    planner_path.write_text(
        """
name: planner
description: Plans the feature.
system_prompt: Produce a plan.
allowed_tools: []
input_keys:
  - user_request
output_key: plan
produces_patches: false
""".strip(),
        encoding="utf-8",
    )
    backend_path = tmp_path / "backend.yaml"
    backend_path.write_text(
        """
name: backend
description: Proposes backend implementation details.
system_prompt: Produce backend changes.
allowed_tools: []
input_keys:
  - user_request
output_key: backend_plan
produces_patches: true
""".strip(),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        """
name: custom_dev
description: Custom dev workflow.
agents:
  - planner.yaml
  - backend.yaml
""".strip(),
        encoding="utf-8",
    )
    return workflow_path


def single_run_directory(base_path: Path) -> Path:
    run_directories = list((base_path / ".agentforge/runs").iterdir())
    assert len(run_directories) == 1
    return run_directories[0]


def read_summary(run_directory: Path) -> dict[str, object]:
    return json.loads((run_directory / "dev_run_summary.json").read_text(encoding="utf-8"))


def read_manifest(run_directory: Path) -> list[dict[str, object]]:
    return json.loads((run_directory / "patch_manifest.json").read_text(encoding="utf-8"))


def snapshot_project(project_root: Path) -> dict[str, str]:
    return {
        path.relative_to(project_root).as_posix(): path.read_text(encoding="utf-8")
        for path in project_root.rglob("*")
        if path.is_file()
    }


def add_venv_to_path(monkeypatch) -> None:
    monkeypatch.setenv(
        "PATH",
        f"{PROJECT_ROOT / '.venv' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    )
