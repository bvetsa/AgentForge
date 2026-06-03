from pathlib import Path

import pytest

from agentforge.tools import ToolError, create_filesystem_tool_registry


def create_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "src").mkdir(parents=True)
    (project_root / "tests").mkdir()
    (project_root / ".git").mkdir()
    (project_root / "node_modules").mkdir()

    (project_root / "README.md").write_text(
        "# Sample FastAPI Project\n\nA tiny todo API.\n",
        encoding="utf-8",
    )
    (project_root / "src/app.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (project_root / "src/models.py").write_text(
        "class Todo:\n    pass\n",
        encoding="utf-8",
    )
    (project_root / "tests/test_app.py").write_text(
        "def test_health():\n    assert True\n",
        encoding="utf-8",
    )
    (project_root / ".git/config").write_text("[core]\n", encoding="utf-8")
    (project_root / "node_modules/package.js").write_text("ignored\n", encoding="utf-8")
    return project_root


def test_list_files_returns_expected_relative_files(tmp_path: Path) -> None:
    registry = create_filesystem_tool_registry(create_project(tmp_path))

    files = registry.get("list_files").run()

    assert files == [
        "README.md",
        "src/app.py",
        "src/models.py",
        "tests/test_app.py",
    ]


def test_read_file_reads_files_inside_project_root(tmp_path: Path) -> None:
    registry = create_filesystem_tool_registry(create_project(tmp_path))

    contents = registry.get("read_file").run(path="README.md")

    assert "Sample FastAPI Project" in contents


def test_read_file_rejects_path_traversal(tmp_path: Path) -> None:
    project_root = create_project(tmp_path)
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    registry = create_filesystem_tool_registry(project_root)

    with pytest.raises(ToolError, match="escapes project root"):
        registry.get("read_file").run(path="../secret.txt")


def test_read_file_rejects_directories(tmp_path: Path) -> None:
    registry = create_filesystem_tool_registry(create_project(tmp_path))

    with pytest.raises(ToolError, match="directory"):
        registry.get("read_file").run(path="src")


def test_search_files_returns_matches_with_line_numbers(tmp_path: Path) -> None:
    registry = create_filesystem_tool_registry(create_project(tmp_path))

    matches = registry.get("search_files").run(query="FastAPI")

    assert matches == [
        {
            "path": "README.md",
            "line_number": 1,
            "line": "# Sample FastAPI Project",
        },
        {
            "path": "src/app.py",
            "line_number": 1,
            "line": "from fastapi import FastAPI",
        },
        {
            "path": "src/app.py",
            "line_number": 3,
            "line": "app = FastAPI()",
        },
    ]


def test_inspect_tree_returns_a_readable_tree(tmp_path: Path) -> None:
    registry = create_filesystem_tool_registry(create_project(tmp_path))

    tree = registry.get("inspect_tree").run()

    assert tree.startswith(".\n")
    assert "src/" in tree
    assert "app.py" in tree
    assert "node_modules" not in tree
