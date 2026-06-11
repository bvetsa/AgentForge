import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.testing import TestRunError, TestRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_test_run_uses_explicit_command_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("Run `make test` before committing.\n")
    tests_directory = project_root / "tests"
    tests_directory.mkdir()
    (tests_directory / "test_sample.py").write_text(
        "def test_sample():\n    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    _add_venv_to_path(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "test",
            "run",
            "--project-root",
            str(project_root),
            "--command",
            "pytest",
        ],
    )

    assert result.exit_code == 0, result.output
    run_directories = list((tmp_path / ".agentforge/test-runs").iterdir())
    assert len(run_directories) == 1
    test_results = json.loads(
        (run_directories[0] / "test_results.json").read_text(encoding="utf-8")
    )
    assert test_results["selected_command"] == ["pytest"]
    assert test_results["command_source"] == "user"
    assert test_results["detection_reason"] == "Explicit --command from user"
    assert test_results["status"] == "passed"
    assert test_results["exit_code"] == 0
    assert test_results["timeout_seconds"] == 30
    assert test_results["timed_out"] is False
    assert test_results["working_directory"] == str(project_root.resolve())
    assert test_results["all_candidates"][0]["source_type"] == "user"


def test_test_run_records_timeout_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    tests_directory = project_root / "tests"
    tests_directory.mkdir(parents=True)
    (tests_directory / "test_slow.py").write_text(
        "import time\n\n\ndef test_slow():\n    time.sleep(2)\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    _add_venv_to_path(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "test",
            "run",
            "--project-root",
            str(project_root),
            "--command",
            "pytest",
            "--timeout",
            "1",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "Status: timeout" in result.output
    assert "Test artifacts:" in result.output
    run_directories = list((tmp_path / ".agentforge/test-runs").iterdir())
    assert len(run_directories) == 1
    test_results_path = run_directories[0] / "test_results.json"
    test_output_path = run_directories[0] / "test_output.txt"
    assert test_results_path.exists()
    assert test_output_path.exists()
    test_results = json.loads(test_results_path.read_text(encoding="utf-8"))
    assert test_results["selected_command"] == ["pytest"]
    assert test_results["command_source"] == "user"
    assert test_results["status"] == "timeout"
    assert test_results["timed_out"] is True
    assert test_results["timeout_seconds"] == 1
    assert test_results["exit_code"] is None
    assert test_results["duration_seconds"] > 0


def test_detection_from_readme_or_contributing_command_mention(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "CONTRIBUTING.md").write_text(
        "Before opening a PR, run `python -m pytest`.\n",
        encoding="utf-8",
    )

    assessment = _first_safe_assessment(project_root)

    assert assessment.candidate.command == ["python", "-m", "pytest"]
    assert assessment.candidate.source_type == "documentation"
    assert assessment.candidate.confidence == 0.90


def test_detection_from_github_actions_workflow(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workflows = project_root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
name: ci
on: [push]
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python -m pip install -e .
          pytest
""".strip(),
        encoding="utf-8",
    )

    assessment = _first_safe_assessment(project_root)

    assert assessment.candidate.command == ["pytest"]
    assert assessment.candidate.source_type == "ci_workflow"
    assert assessment.candidate.confidence == 0.95


def test_detection_from_makefile_test_target(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "Makefile").write_text(
        "test:\n\tpytest\n",
        encoding="utf-8",
    )

    assessment = _first_safe_assessment(project_root)

    assert assessment.candidate.command == ["make", "test"]
    assert assessment.candidate.source_type == "make_target"
    assert assessment.candidate.confidence == 0.80


def test_detection_from_package_json_test_script(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )

    assessment = _first_safe_assessment(project_root)

    assert assessment.candidate.command == ["npm", "test"]
    assert assessment.candidate.source_type == "package_json_script"
    assert assessment.candidate.confidence == 0.75


def test_detection_from_python_test_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    tests_directory = project_root / "tests"
    tests_directory.mkdir(parents=True)
    (tests_directory / "test_app.py").write_text(
        "def test_app():\n    assert True\n",
        encoding="utf-8",
    )

    assessment = _first_safe_assessment(project_root)

    assert assessment.candidate.command == ["python", "-m", "pytest"]
    assert assessment.candidate.source_type == "python_default"
    assert assessment.candidate.confidence == 0.50


def test_no_detection_case_writes_clear_failure_artifact(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("No test instructions yet.\n", encoding="utf-8")
    runner = TestRunner(runs_directory=tmp_path / "test-runs")

    with pytest.raises(TestRunError, match="No safe test command detected") as error:
        runner.run(project_root)

    assert error.value.run_directory is not None
    test_results = json.loads(
        (error.value.run_directory / "test_results.json").read_text(encoding="utf-8")
    )
    assert test_results["selected_command"] is None
    assert test_results["command_source"] == "detected"
    assert test_results["status"] == "no_command_detected"
    assert test_results["exit_code"] is None
    assert test_results["all_candidates"] == []


def test_unsafe_detected_command_is_rejected(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        "```bash\npytest && rm -rf /\n```\n",
        encoding="utf-8",
    )
    runner = TestRunner(runs_directory=tmp_path / "test-runs")

    with pytest.raises(TestRunError, match="No safe test command detected") as error:
        runner.run(project_root)

    assert error.value.run_directory is not None
    test_results = json.loads(
        (error.value.run_directory / "test_results.json").read_text(encoding="utf-8")
    )
    assert test_results["selected_command"] is None
    assert test_results["status"] == "no_command_detected"
    assert test_results["all_candidates"][0]["command"] == [
        "pytest",
        "&&",
        "rm",
        "-rf",
        "/",
    ]
    assert test_results["all_candidates"][0]["safe"] is False
    assert "dangerous shell syntax" in test_results["all_candidates"][0]["rejection_reason"]


def test_detected_working_directory_must_stay_inside_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workflows = project_root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
name: ci
on: [push]
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - working-directory: ..
        run: pytest
""".strip(),
        encoding="utf-8",
    )
    runner = TestRunner(runs_directory=tmp_path / "test-runs")

    with pytest.raises(TestRunError, match="No safe test command detected") as error:
        runner.run(project_root)

    assert error.value.run_directory is not None
    test_results = json.loads(
        (error.value.run_directory / "test_results.json").read_text(encoding="utf-8")
    )
    assert test_results["all_candidates"][0]["command"] == ["pytest"]
    assert test_results["all_candidates"][0]["safe"] is False
    assert (
        test_results["all_candidates"][0]["rejection_reason"]
        == "working directory resolves outside project_root"
    )


def _first_safe_assessment(project_root: Path):
    assessments = TestRunner().detect_candidates(project_root)
    safe_assessments = [
        assessment for assessment in assessments if assessment.safety.is_safe
    ]
    assert safe_assessments
    return safe_assessments[0]


def _add_venv_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PATH",
        f"{PROJECT_ROOT / '.venv' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    )
