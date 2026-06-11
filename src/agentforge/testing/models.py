"""Data models for test command detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceCommand:
    """A command-like project signal discovered during scanning."""

    command: str
    source_type: str
    source_path: str
    line: int | None = None
    working_directory: str = "."
    reason: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "command": self.command,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "line": self.line,
            "working_directory": self.working_directory,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ProjectEvidence:
    """Evidence collected from a project tree before command detection."""

    project_root: Path
    file_tree: list[str]
    detected_extensions: dict[str, int]
    package_files: list[str]
    test_files: list[str]
    test_directories: list[str]
    documentation_commands: list[EvidenceCommand]
    ci_commands: list[EvidenceCommand]
    make_test_targets: list[EvidenceCommand]
    package_json_scripts: list[EvidenceCommand]
    python_indicators: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "project_root": str(self.project_root),
            "file_tree": self.file_tree,
            "detected_extensions": self.detected_extensions,
            "package_files": self.package_files,
            "test_files": self.test_files,
            "test_directories": self.test_directories,
            "documentation_commands": [
                command.to_dict() for command in self.documentation_commands
            ],
            "ci_commands": [command.to_dict() for command in self.ci_commands],
            "make_test_targets": [
                command.to_dict() for command in self.make_test_targets
            ],
            "package_json_scripts": [
                command.to_dict() for command in self.package_json_scripts
            ],
            "python_indicators": self.python_indicators,
        }


@dataclass(frozen=True)
class TestCommandCandidate:
    """A ranked test command candidate produced from project evidence."""

    command: list[str]
    working_directory: Path
    confidence: float
    reason: str
    source_type: str
    evidence_path: str | None = None
    evidence_line: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self, project_root: Path | None = None) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        working_directory = self.working_directory.resolve(strict=False)
        data: dict[str, Any] = {
            "command": self.command,
            "working_directory": str(working_directory),
            "confidence": self.confidence,
            "reason": self.reason,
            "source_type": self.source_type,
            "evidence_path": self.evidence_path,
            "evidence_line": self.evidence_line,
            "metadata": self.metadata,
        }
        if project_root is not None:
            root = project_root.resolve(strict=False)
            try:
                data["working_directory_relative"] = (
                    working_directory.relative_to(root).as_posix() or "."
                )
            except ValueError:
                data["working_directory_relative"] = None
        return data
