"""Sandboxed read-only filesystem tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentforge.tools.base import Tool, ToolError
from agentforge.tools.registry import ToolRegistry

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
}
MAX_FILE_SIZE_BYTES = 100 * 1024
MAX_SEARCH_RESULTS = 50
DEFAULT_TREE_DEPTH = 4


def create_filesystem_tool_registry(project_root: str | Path) -> ToolRegistry:
    """Create a registry containing the read-only filesystem tools."""
    sandbox = FilesystemSandbox(project_root)
    registry = ToolRegistry()
    registry.register(ListFilesTool(sandbox))
    registry.register(ReadFileTool(sandbox))
    registry.register(SearchFilesTool(sandbox))
    registry.register(InspectTreeTool(sandbox))
    return registry


@dataclass(frozen=True)
class FilesystemSandbox:
    """Resolve all tool paths against one project root."""

    project_root: Path

    def __init__(self, project_root: str | Path) -> None:
        root = Path(project_root).expanduser().resolve()
        if not root.exists():
            raise ToolError(f"Project root does not exist: {project_root}")
        if not root.is_dir():
            raise ToolError(f"Project root is not a directory: {project_root}")
        object.__setattr__(self, "project_root", root)

    def resolve_file(self, path: str | Path) -> Path:
        """Resolve a relative file path and reject sandbox escapes."""
        requested_path = Path(path)
        if requested_path.is_absolute():
            raise ToolError("Absolute paths are not allowed")

        try:
            resolved_path = (self.project_root / requested_path).resolve(strict=True)
            resolved_path.relative_to(self.project_root)
        except FileNotFoundError as error:
            raise ToolError(f"File does not exist: {path}") from error
        except ValueError as error:
            raise ToolError(f"Path escapes project root: {path}") from error

        if resolved_path.is_dir():
            raise ToolError(f"Path is a directory: {path}")
        if not resolved_path.is_file():
            raise ToolError(f"Path is not a file: {path}")
        return resolved_path

    def iter_files(self) -> list[Path]:
        """Return files under the project root while ignoring junk directories."""
        files: list[Path] = []
        for current_root, directories, filenames in os.walk(self.project_root, followlinks=False):
            directories[:] = sorted(
                directory for directory in directories if directory not in IGNORED_DIRECTORIES
            )
            for filename in sorted(filenames):
                path = Path(current_root) / filename
                if self._is_safe_file(path):
                    files.append(path)
        return files

    def relative_path(self, path: Path) -> str:
        """Return a POSIX-style path relative to the project root."""
        return path.relative_to(self.project_root).as_posix()

    def read_text_file(self, path: str | Path) -> str:
        """Read a UTF-8 text file after applying sandbox and size checks."""
        resolved_path = self.resolve_file(path)
        if resolved_path.stat().st_size > MAX_FILE_SIZE_BYTES:
            raise ToolError(f"File is larger than {MAX_FILE_SIZE_BYTES} bytes: {path}")

        try:
            return resolved_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ToolError(f"File is not valid UTF-8 text: {path}") from error

    def _is_safe_file(self, path: Path) -> bool:
        try:
            resolved_path = path.resolve(strict=True)
            resolved_path.relative_to(self.project_root)
        except (FileNotFoundError, ValueError):
            return False
        return resolved_path.is_file()


@dataclass(frozen=True)
class ListFilesTool(Tool):
    """List project files as relative paths."""

    sandbox: FilesystemSandbox
    name: str = "list_files"
    description: str = "Recursively list files under the project root."

    def run(self, **kwargs: Any) -> list[str]:
        _reject_unexpected_arguments(kwargs)
        return [self.sandbox.relative_path(path) for path in self.sandbox.iter_files()]


@dataclass(frozen=True)
class ReadFileTool(Tool):
    """Read one UTF-8 text file from the project."""

    sandbox: FilesystemSandbox
    name: str = "read_file"
    description: str = "Read one file under the project root."

    def run(self, **kwargs: Any) -> str:
        path = _require_string(kwargs, "path")
        return self.sandbox.read_text_file(path)


@dataclass(frozen=True)
class SearchFilesTool(Tool):
    """Search text files for a query string."""

    sandbox: FilesystemSandbox
    name: str = "search_files"
    description: str = "Search text files under the project root."

    def run(self, **kwargs: Any) -> list[dict[str, str | int]]:
        query = _require_string(kwargs, "query")
        if not query:
            return []

        matches: list[dict[str, str | int]] = []
        normalized_query = query.casefold()
        for path in self.sandbox.iter_files():
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if normalized_query in line.casefold():
                    matches.append(
                        {
                            "path": self.sandbox.relative_path(path),
                            "line_number": line_number,
                            "line": line,
                        }
                    )
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return matches
        return matches


@dataclass(frozen=True)
class InspectTreeTool(Tool):
    """Return a readable project tree."""

    sandbox: FilesystemSandbox
    name: str = "inspect_tree"
    description: str = "Return a readable project directory tree."

    def run(self, **kwargs: Any) -> str:
        max_depth = kwargs.pop("max_depth", DEFAULT_TREE_DEPTH)
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise ToolError(f"Unexpected tool arguments: {unexpected}")
        if not isinstance(max_depth, int):
            raise ToolError("max_depth must be an integer")
        if max_depth < 0:
            raise ToolError("max_depth must be non-negative")

        return "\n".join(self._build_tree(max_depth))

    def _build_tree(self, max_depth: int) -> list[str]:
        lines = ["."]
        self._append_directory(
            self.sandbox.project_root,
            prefix="",
            depth=0,
            max_depth=max_depth,
            lines=lines,
        )
        return lines

    def _append_directory(
        self,
        directory: Path,
        *,
        prefix: str,
        depth: int,
        max_depth: int,
        lines: list[str],
    ) -> None:
        if depth >= max_depth:
            return

        entries = self._visible_entries(directory)
        for index, entry in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            child_prefix = "    " if is_last else "|   "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir():
                self._append_directory(
                    entry,
                    prefix=f"{prefix}{child_prefix}",
                    depth=depth + 1,
                    max_depth=max_depth,
                    lines=lines,
                )

    def _visible_entries(self, directory: Path) -> list[Path]:
        entries: list[Path] = []
        for entry in directory.iterdir():
            if entry.is_dir() and entry.name in IGNORED_DIRECTORIES:
                continue
            if entry.is_symlink():
                continue
            entries.append(entry)
        return sorted(entries, key=lambda entry: (not entry.is_dir(), entry.name.lower()))


def _require_string(kwargs: dict[str, Any], key: str) -> str:
    value = kwargs.pop(key, None)
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise ToolError(f"Unexpected tool arguments: {unexpected}")
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string")
    return value


def _reject_unexpected_arguments(kwargs: dict[str, Any]) -> None:
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise ToolError(f"Unexpected tool arguments: {unexpected}")
