import json
from pathlib import Path

from typer.testing import CliRunner

from agentforge.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_patch_list_displays_available_patches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                agent_name="backend",
                target_file="src/app.py",
                title="Update app",
                diff=replace_line_diff("src/app.py", "old", "new"),
            ),
            patch_entry(
                patch_id="002-tests",
                agent_name="testing",
                target_file="tests/test_app.py",
                title="Update tests",
                diff=replace_line_diff("tests/test_app.py", "old", "new"),
            ),
        ],
    )

    result = CliRunner().invoke(app, ["patch", "list", "run-1"])

    assert result.exit_code == 0
    assert "ID\tAgent\tTarget file\tStatus\tTitle" in result.stdout
    assert "001-backend\tbackend\tsrc/app.py\tproposed\tUpdate app" in result.stdout
    assert "002-tests\ttesting\ttests/test_app.py\tproposed\tUpdate tests" in result.stdout


def test_patch_show_displays_patch_contents(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_sample_project(tmp_path)
    before = snapshot_project_files(project_root)
    diff = replace_line_diff("src/app.py", 'print("old")', 'print("new")')
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="src/app.py",
                diff=diff,
            ),
        ],
    )

    result = CliRunner().invoke(app, ["patch", "show", "run-1", "001-backend"])

    assert result.exit_code == 0
    assert result.stdout.strip() == diff
    assert snapshot_project_files(project_root) == before
    assert not (project_root / "proposed").exists()


def test_patch_apply_modifies_only_the_intended_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    (project_root / "src").mkdir(parents=True)
    target_file = project_root / "src/app.py"
    other_file = project_root / "src/other.py"
    target_file.write_text('print("old")\n', encoding="utf-8")
    other_file.write_text("keep me\n", encoding="utf-8")
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="src/app.py",
                diff=replace_line_diff("src/app.py", 'print("old")', 'print("new")'),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 0
    assert target_file.read_text(encoding="utf-8") == 'print("new")\n'
    assert other_file.read_text(encoding="utf-8") == "keep me\n"
    assert not (project_root / "proposed").exists()


def test_patch_apply_uses_manifest_target_file_not_agent_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    (project_root / "src").mkdir(parents=True)
    (project_root / "tests").mkdir()
    app_file = project_root / "src/app.py"
    test_file = project_root / "tests/test_app.py"
    app_file.write_text("app stays here\n", encoding="utf-8")
    test_file.write_text("old test\n", encoding="utf-8")
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-arbitrary",
                agent_name="frontend",
                target_file="tests/test_app.py",
                diff=replace_line_diff("tests/test_app.py", "old test", "new test"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-arbitrary", "--project-root", str(project_root)],
    )

    assert result.exit_code == 0
    assert test_file.read_text(encoding="utf-8") == "new test\n"
    assert app_file.read_text(encoding="utf-8") == "app stays here\n"


def test_patch_apply_rejects_missing_patch_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="src/app.py",
                diff=new_file_diff("src/app.py", "created"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "missing", "--project-root", str(project_root)],
    )

    assert result.exit_code == 1
    assert "Patch ID 'missing' does not exist" in result.stderr
    assert not (project_root / "src/app.py").exists()


def test_patch_apply_rejects_missing_patch_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    run_directory = write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="src/app.py",
                diff=new_file_diff("src/app.py", "created"),
            ),
        ],
    )
    (run_directory / "patches/001-backend.diff").unlink()

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 1
    assert "Patch file does not exist" in result.stderr
    assert not (project_root / "src/app.py").exists()


def test_patch_apply_rejects_absolute_target_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    absolute_target = tmp_path / "outside.txt"
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file=str(absolute_target),
                diff=new_file_diff("src/app.py", "created"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 1
    assert "must not be absolute" in result.stderr
    assert not absolute_target.exists()


def test_patch_apply_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="../outside.txt",
                diff=new_file_diff("../outside.txt", "outside"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 1
    assert "cannot contain traversal" in result.stderr
    assert not (tmp_path / "outside.txt").exists()


def test_patch_apply_rejects_proposed_targets_inside_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="proposed/backend.txt",
                diff=new_file_diff("proposed/backend.txt", "proposal text"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 1
    assert "must not write proposal files" in result.stderr
    assert not (project_root / "proposed").exists()


def test_patch_apply_does_not_write_outside_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    outside_root = tmp_path / "outside"
    project_root.mkdir()
    outside_root.mkdir()
    (project_root / "linked").symlink_to(outside_root, target_is_directory=True)
    write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="linked/escape.txt",
                diff=new_file_diff("linked/escape.txt", "outside"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 1
    assert "escapes project root" in result.stderr
    assert not (outside_root / "escape.txt").exists()


def test_patch_manifest_status_updates_after_apply(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    run_directory = write_patch_run(
        tmp_path,
        "run-1",
        [
            patch_entry(
                patch_id="001-backend",
                target_file="notes.txt",
                diff=new_file_diff("notes.txt", "created"),
            ),
        ],
    )

    result = CliRunner().invoke(
        app,
        ["patch", "apply", "run-1", "001-backend", "--project-root", str(project_root)],
    )

    assert result.exit_code == 0
    manifest = json.loads((run_directory / "patch_manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["status"] == "applied"
    assert (project_root / "notes.txt").read_text(encoding="utf-8") == "created\n"


def test_agentforge_run_generates_real_target_patch_artifacts_without_applying(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_sample_project(tmp_path)
    before = snapshot_project_files(project_root)

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(PROJECT_ROOT / "examples/workflows/basic_feature.yaml"),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--project-root",
            str(project_root),
        ],
    )

    assert result.exit_code == 0
    assert snapshot_project_files(project_root) == before
    assert not (project_root / "proposed").exists()

    run_directory = next((tmp_path / ".agentforge/runs").iterdir())
    manifest = json.loads((run_directory / "patch_manifest.json").read_text(encoding="utf-8"))
    target_files = {entry["target_file"] for entry in manifest}
    assert target_files == {"src/app.py", "src/models.py", "tests/test_app.py"}
    assert all(not entry["target_file"].startswith("proposed/") for entry in manifest)
    for entry in manifest:
        diff_text = (run_directory / entry["patch_file"]).read_text(encoding="utf-8")
        assert f"--- a/{entry['target_file']}" in diff_text
        assert f"+++ b/{entry['target_file']}" in diff_text


def test_patch_apply_after_run_modifies_real_target_and_not_proposed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_root = create_sample_project(tmp_path)
    run_result = CliRunner().invoke(
        app,
        [
            "run",
            str(PROJECT_ROOT / "examples/workflows/basic_feature.yaml"),
            "--input",
            "Add a todo endpoint to a FastAPI app",
            "--project-root",
            str(project_root),
        ],
    )
    assert run_result.exit_code == 0
    run_directory = next((tmp_path / ".agentforge/runs").iterdir())
    manifest_path = run_directory / "patch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patch_entry_for_app = next(entry for entry in manifest if entry["target_file"] == "src/app.py")
    before_app = (project_root / "src/app.py").read_text(encoding="utf-8")
    before_models = (project_root / "src/models.py").read_text(encoding="utf-8")

    apply_result = CliRunner().invoke(
        app,
        [
            "patch",
            "apply",
            "--project-root",
            str(project_root),
            run_directory.name,
            patch_entry_for_app["id"],
        ],
    )

    assert apply_result.exit_code == 0
    after_app = (project_root / "src/app.py").read_text(encoding="utf-8")
    assert after_app != before_app
    assert patch_entry_for_app["title"] in after_app
    assert (project_root / "src/models.py").read_text(encoding="utf-8") == before_models
    assert not (project_root / "proposed").exists()

    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated_patch = next(
        entry for entry in updated_manifest if entry["id"] == patch_entry_for_app["id"]
    )
    assert updated_patch["status"] == "applied"
    assert [
        entry["status"]
        for entry in updated_manifest
        if entry["id"] != patch_entry_for_app["id"]
    ] == ["proposed", "proposed"]


def write_patch_run(tmp_path: Path, run_id: str, entries: list[dict[str, str]]) -> Path:
    run_directory = tmp_path / ".agentforge/runs" / run_id
    patches_directory = run_directory / "patches"
    patches_directory.mkdir(parents=True)
    for entry in entries:
        (run_directory / entry["patch_file"]).write_text(f"{entry['diff']}\n", encoding="utf-8")
    (run_directory / "patch_manifest.json").write_text(
        f"{json.dumps(entries, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return run_directory


def patch_entry(
    *,
    patch_id: str,
    target_file: str,
    diff: str,
    agent_name: str = "backend",
    title: str = "Patch title",
) -> dict[str, str]:
    return {
        "id": patch_id,
        "agent_name": agent_name,
        "title": title,
        "description": "Test patch proposal.",
        "target_file": target_file,
        "patch_file": f"patches/{patch_id}.diff",
        "status": "proposed",
        "diff": diff,
    }


def replace_line_diff(target_file: str, old_line: str, new_line: str) -> str:
    return "\n".join(
        [
            f"diff --git a/{target_file} b/{target_file}",
            f"--- a/{target_file}",
            f"+++ b/{target_file}",
            "@@ -1 +1 @@",
            f"-{old_line}",
            f"+{new_line}",
        ]
    )


def create_sample_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "src").mkdir(parents=True)
    (project_root / "tests").mkdir()
    (project_root / "src/app.py").write_text(
        "\n".join(
            [
                "from fastapi import FastAPI",
                "from src.models import Todo",
                "",
                "app = FastAPI()",
                "",
                "TODOS: list[Todo] = []",
                "",
                "",
                '@app.get("/health")',
                "def health() -> dict[str, str]:",
                '    return {"status": "ok"}',
                "",
                "",
                '@app.get("/todos")',
                "def list_todos() -> list[Todo]:",
                "    return TODOS",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "src/models.py").write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "",
                "",
                "class Todo(BaseModel):",
                "    id: int",
                "    title: str",
                "    completed: bool = False",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "tests/test_app.py").write_text(
        "\n".join(
            [
                "from src.app import health",
                "",
                "",
                "def test_health() -> None:",
                '    assert health() == {"status": "ok"}',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return project_root


def snapshot_project_files(project_root: Path) -> dict[str, str]:
    return {
        path.relative_to(project_root).as_posix(): path.read_text(encoding="utf-8")
        for path in project_root.rglob("*")
        if path.is_file()
    }


def new_file_diff(target_file: str, new_line: str) -> str:
    return "\n".join(
        [
            f"diff --git a/{target_file} b/{target_file}",
            f"--- a/{target_file}",
            f"+++ b/{target_file}",
            "@@ -0,0 +1 @@",
            f"+{new_line}",
        ]
    )
