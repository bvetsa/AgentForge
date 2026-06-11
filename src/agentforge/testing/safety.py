"""Safety checks for detected and user-provided test commands."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


class CommandParseError(ValueError):
    """Raised when a command string cannot be tokenized safely."""


@dataclass(frozen=True)
class CommandValidationResult:
    """Result of validating a command candidate."""

    is_safe: bool
    reason: str | None = None


def split_command(command: str) -> list[str]:
    """Split a command string into argv form without invoking a shell."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as error:
        raise CommandParseError(str(error)) from error
    if not argv:
        raise CommandParseError("command is empty")
    return argv


def contains_dangerous_shell_syntax(value: str) -> bool:
    """Return True when a string contains shell composition or redirection syntax."""
    dangerous_substrings = ("&&", "||", ";", "|", ">", "<", "`", "$(", "\n", "\r")
    return any(substring in value for substring in dangerous_substrings)


class CommandSafetyValidator:
    """Validate test commands before they are executed with shell=False."""

    _python_executables = {"python", "python3"}

    def validate(
        self,
        *,
        command: list[str],
        working_directory: Path,
        project_root: Path,
        metadata: dict[str, str] | None = None,
    ) -> CommandValidationResult:
        """Validate argv form, working directory, and optional source metadata."""
        if not command:
            return CommandValidationResult(False, "command is empty")

        metadata = metadata or {}
        root = project_root.resolve(strict=False)
        resolved_working_directory = working_directory.resolve(strict=False)
        if not _is_relative_to(resolved_working_directory, root):
            return CommandValidationResult(
                False,
                "working directory resolves outside project_root",
            )
        if not resolved_working_directory.exists() or not resolved_working_directory.is_dir():
            return CommandValidationResult(False, "working directory does not exist")

        unsafe_token = self._find_unsafe_token(command)
        if unsafe_token is not None:
            return CommandValidationResult(
                False,
                f"command contains dangerous shell syntax: {unsafe_token}",
            )

        for metadata_key in ("script", "make_recipe"):
            source_command = metadata.get(metadata_key)
            if source_command and contains_dangerous_shell_syntax(source_command):
                return CommandValidationResult(
                    False,
                    f"{metadata_key} contains dangerous shell syntax",
                )

        if not self._matches_allowed_command_form(command):
            return CommandValidationResult(
                False,
                "command is not an allowed deterministic test command form",
            )

        return CommandValidationResult(True)

    @classmethod
    def _find_unsafe_token(cls, command: list[str]) -> str | None:
        for token in command:
            if contains_dangerous_shell_syntax(token):
                return token
            if token.startswith("/") or _has_parent_directory_reference(token):
                return token
        return None

    @classmethod
    def _matches_allowed_command_form(cls, command: list[str]) -> bool:
        executable = command[0]
        if executable == "pytest":
            return True

        if executable in cls._python_executables and len(command) >= 3:
            if command[1:3] == ["-m", "pytest"]:
                return True
            if command[1:3] == ["manage.py", "test"]:
                return True

        if executable == "npm":
            return command[1:2] == ["test"] or command[1:3] == ["run", "test"]

        return command == ["make", "test"]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _has_parent_directory_reference(token: str) -> bool:
    parts = token.replace("\\", "/").split("/")
    return ".." in parts
