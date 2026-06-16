"""Project scanner for deterministic test command evidence."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from agentforge.testing.models import EvidenceCommand, ProjectEvidence


class ProjectScanError(RuntimeError):
    """Raised when a project cannot be scanned."""


class ProjectScanner:
    """Collect project evidence that may identify a likely test command."""

    _ignored_directories = {
        ".agentforge",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
    _package_file_names = {
        "Makefile",
        "GNUmakefile",
        "makefile",
        "manage.py",
        "package.json",
        "pyproject.toml",
        "pytest.ini",
        "requirements-dev.txt",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
        "tox.ini",
    }
    _test_directory_names = {"__tests__", "spec", "test", "tests"}
    _documentation_names = {"README.md", "CONTRIBUTING.md"}
    _workflow_suffixes = {".yml", ".yaml"}

    def scan(self, project_root: str | Path) -> ProjectEvidence:
        """Scan a project directory and return structured evidence."""
        root = Path(project_root).resolve()
        if not root.exists() or not root.is_dir():
            raise ProjectScanError(f"project root does not exist or is not a directory: {root}")

        files = self._list_project_files(root)
        file_tree = [path.relative_to(root).as_posix() for path in files]
        detected_extensions = Counter(path.suffix for path in files if path.suffix)
        package_files = self._detect_package_files(root, files)
        test_files = self._detect_test_files(root, files)
        test_directories = self._detect_test_directories(root, files)
        documentation_commands = self._scan_documentation(root, files)
        ci_commands = self._scan_github_actions(root)
        make_test_targets = self._scan_makefiles(root, files)
        package_json_scripts = self._scan_package_json(root, files)
        python_indicators = self._detect_python_indicators(root, files, file_tree)

        return ProjectEvidence(
            project_root=root,
            file_tree=file_tree,
            detected_extensions=dict(sorted(detected_extensions.items())),
            package_files=package_files,
            test_files=test_files,
            test_directories=test_directories,
            documentation_commands=documentation_commands,
            ci_commands=ci_commands,
            make_test_targets=make_test_targets,
            package_json_scripts=package_json_scripts,
            python_indicators=python_indicators,
        )

    def _list_project_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for directory, directory_names, file_names in os.walk(root):
            directory_path = Path(directory)
            directory_names[:] = [
                name for name in directory_names if name not in self._ignored_directories
            ]
            for file_name in file_names:
                files.append(directory_path / file_name)
        return sorted(files)

    def _detect_package_files(self, root: Path, files: list[Path]) -> list[str]:
        package_files: list[str] = []
        for path in files:
            relative = path.relative_to(root).as_posix()
            if path.name in self._package_file_names or relative.startswith(".github/workflows/"):
                package_files.append(relative)
        return package_files

    def _detect_test_files(self, root: Path, files: list[Path]) -> list[str]:
        test_files: list[str] = []
        for path in files:
            name = path.name
            if (
                name.startswith("test_")
                or name.endswith("_test.py")
                or ".test." in name
                or ".spec." in name
            ):
                test_files.append(path.relative_to(root).as_posix())
        return test_files

    def _detect_test_directories(self, root: Path, files: list[Path]) -> list[str]:
        directories: set[str] = set()
        for path in files:
            relative = path.relative_to(root)
            for index, part in enumerate(relative.parts[:-1]):
                if part in self._test_directory_names:
                    directories.add(Path(*relative.parts[: index + 1]).as_posix())
        return sorted(directories)

    def _scan_documentation(self, root: Path, files: list[Path]) -> list[EvidenceCommand]:
        commands: list[EvidenceCommand] = []
        for path in files:
            if path.name not in self._documentation_names:
                continue
            text = _read_text(path)
            if text is None:
                continue
            relative = path.relative_to(root).as_posix()
            commands.extend(
                _extract_test_command_mentions(
                    text=text,
                    source_path=relative,
                    source_type="documentation",
                    reason=f"{relative} documents a test command",
                )
            )
        return _deduplicate_evidence(commands)

    def _scan_github_actions(self, root: Path) -> list[EvidenceCommand]:
        workflow_directory = root / ".github" / "workflows"
        if not workflow_directory.exists():
            return []

        commands: list[EvidenceCommand] = []
        for path in sorted(workflow_directory.glob("*")):
            if path.suffix not in self._workflow_suffixes or not path.is_file():
                continue
            text = _read_text(path)
            if text is None:
                continue
            workflow = _load_yaml(text)
            if not isinstance(workflow, dict):
                continue
            relative = path.relative_to(root).as_posix()
            commands.extend(
                self._extract_workflow_run_commands(
                    workflow=workflow,
                    source_path=relative,
                    workflow_text=text,
                )
            )
        return _deduplicate_evidence(commands)

    def _extract_workflow_run_commands(
        self,
        *,
        workflow: dict[str, Any],
        source_path: str,
        workflow_text: str,
    ) -> list[EvidenceCommand]:
        commands: list[EvidenceCommand] = []
        default_working_directory = _workflow_working_directory(workflow.get("defaults"))
        jobs = workflow.get("jobs", {})
        if not isinstance(jobs, dict):
            return commands

        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            job_working_directory = (
                _workflow_working_directory(job.get("defaults")) or default_working_directory
            )
            steps = job.get("steps", [])
            if not isinstance(steps, list):
                continue
            for step in steps:
                if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                    continue
                working_directory = (
                    step.get("working-directory")
                    or job_working_directory
                    or "."
                )
                if not isinstance(working_directory, str):
                    working_directory = "."
                run_command = step["run"]
                for line in run_command.splitlines():
                    command = _extract_known_test_command(line)
                    if command is None:
                        continue
                    commands.append(
                        EvidenceCommand(
                            command=command,
                            source_type="ci_workflow",
                            source_path=source_path,
                            line=_line_number_for_text(workflow_text, line),
                            working_directory=working_directory,
                            reason=f"{source_path} runs a test command in CI",
                        )
                    )
        return commands

    def _scan_makefiles(self, root: Path, files: list[Path]) -> list[EvidenceCommand]:
        commands: list[EvidenceCommand] = []
        makefiles = {
            path
            for path in files
            if path.name in {"Makefile", "GNUmakefile", "makefile"}
        }
        for path in sorted(makefiles):
            text = _read_text(path)
            if text is None:
                continue
            target = _extract_make_test_target(text)
            if target is None:
                continue
            line_number, recipe = target
            relative = path.relative_to(root).as_posix()
            commands.append(
                EvidenceCommand(
                    command="make test",
                    source_type="make_target",
                    source_path=relative,
                    line=line_number,
                    working_directory=_relative_directory(root, path.parent),
                    reason=f"{relative} defines a test target",
                    metadata={"make_recipe": recipe},
                )
            )
        return commands

    def _scan_package_json(self, root: Path, files: list[Path]) -> list[EvidenceCommand]:
        commands: list[EvidenceCommand] = []
        for path in files:
            if path.name != "package.json":
                continue
            text = _read_text(path)
            if text is None:
                continue
            try:
                package = json.loads(text)
            except json.JSONDecodeError:
                continue
            scripts = package.get("scripts")
            if not isinstance(scripts, dict) or not isinstance(scripts.get("test"), str):
                continue
            relative = path.relative_to(root).as_posix()
            commands.append(
                EvidenceCommand(
                    command="npm test",
                    source_type="package_json_script",
                    source_path=relative,
                    working_directory=_relative_directory(root, path.parent),
                    reason=f"{relative} defines a test script",
                    metadata={"script": scripts["test"]},
                )
            )
        return commands

    def _detect_python_indicators(
        self,
        root: Path,
        files: list[Path],
        file_tree: list[str],
    ) -> dict[str, bool]:
        python_files = [path for path in files if path.suffix == ".py"]
        package_text = "\n".join(
            _read_text(path) or ""
            for path in files
            if path.name in {"pyproject.toml", "pytest.ini", "requirements.txt"}
        )
        return {
            "has_python_files": bool(python_files),
            "has_python_test_files": any(
                path.endswith(".py") for path in self._detect_test_files(root, files)
            ),
            "has_tests_directory": any(
                directory == "tests" for directory in self._detect_test_directories(root, files)
            ),
            "has_manage_py": "manage.py" in file_tree,
            "mentions_django": "django" in package_text.lower(),
            "mentions_pytest": "pytest" in package_text.lower(),
        }


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _load_yaml(text: str) -> Any:
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}


def _extract_test_command_mentions(
    *,
    text: str,
    source_path: str,
    source_type: str,
    reason: str,
) -> list[EvidenceCommand]:
    commands: list[EvidenceCommand] = []
    in_fenced_block = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fenced_block = not in_fenced_block
            continue

        if in_fenced_block:
            command = _extract_known_test_command(line)
            if command is not None:
                commands.append(
                    EvidenceCommand(
                        command=command,
                        source_type=source_type,
                        source_path=source_path,
                        line=line_number,
                        reason=reason,
                    )
                )

        for inline_command in re.findall(r"`([^`]+)`", line):
            command = _extract_known_test_command(inline_command)
            if command is not None:
                commands.append(
                    EvidenceCommand(
                        command=command,
                        source_type=source_type,
                        source_path=source_path,
                        line=line_number,
                        reason=reason,
                    )
                )
    return commands


def _extract_known_test_command(line: str) -> str | None:
    normalized = _strip_prompt(line)
    if not normalized:
        return None

    command_patterns = (
        r"python3?\s+-m\s+pytest(?:\s+[^#`\n]+)?",
        r"python3?\s+manage\.py\s+test(?:\s+[^#`\n]+)?",
        r"npm\s+run\s+test(?:\s+[^#`\n]+)?",
        r"npm\s+test(?:\s+[^#`\n]+)?",
        r"make\s+test(?:\s+[^#`\n]+)?",
        r"pytest(?:\s+[^#`\n]+)?",
    )
    for pattern in command_patterns:
        match = re.match(pattern, normalized)
        if match is not None:
            return match.group(0).strip()
    return None


def _strip_prompt(line: str) -> str:
    stripped = line.strip()
    for prompt in ("$", "%", ">"):
        if stripped.startswith(f"{prompt} "):
            return stripped[2:].strip()
    return stripped


def _workflow_working_directory(defaults: Any) -> str | None:
    if not isinstance(defaults, dict):
        return None
    run_defaults = defaults.get("run")
    if not isinstance(run_defaults, dict):
        return None
    working_directory = run_defaults.get("working-directory")
    return working_directory if isinstance(working_directory, str) else None


def _line_number_for_text(text: str, needle: str) -> int | None:
    stripped_needle = needle.strip()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == stripped_needle:
            return line_number
    return None


def _extract_make_test_target(text: str) -> tuple[int, str] | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^test\s*:", line):
            continue
        recipe_lines: list[str] = []
        for recipe_line in lines[index + 1 :]:
            if not recipe_line.strip():
                continue
            if recipe_line.startswith(("\t", " ")):
                recipe_lines.append(recipe_line.strip())
                continue
            break
        return index + 1, "\n".join(recipe_lines)
    return None


def _relative_directory(root: Path, directory: Path) -> str:
    relative = directory.relative_to(root).as_posix()
    return relative or "."


def _deduplicate_evidence(commands: list[EvidenceCommand]) -> list[EvidenceCommand]:
    deduplicated: list[EvidenceCommand] = []
    seen: set[tuple[str, str, str, int | None, str]] = set()
    for command in commands:
        key = (
            command.command,
            command.source_type,
            command.source_path,
            command.line,
            command.working_directory,
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(command)
    return deduplicated
