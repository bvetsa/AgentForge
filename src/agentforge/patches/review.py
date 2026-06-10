"""Review and apply human-approved patch proposals."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from agentforge.patches.models import PatchProposal


class PatchReviewError(RuntimeError):
    """Raised when a patch proposal cannot be reviewed or applied safely."""


@dataclass(frozen=True)
class HunkLine:
    """One line inside a unified diff hunk."""

    kind: str
    text: str


@dataclass(frozen=True)
class Hunk:
    """A parsed unified diff hunk."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[HunkLine]


@dataclass(frozen=True)
class ParsedDiff:
    """A parsed single-file unified diff."""

    source_path: str
    target_path: str
    hunks: list[Hunk]


class PatchReviewService:
    """Load, inspect, and apply patch proposal artifacts."""

    def __init__(self, runs_directory: str | Path = ".agentforge/runs") -> None:
        self.runs_directory = Path(runs_directory)

    def list_patches(self, run_id: str) -> list[PatchProposal]:
        """Return patch proposals for a run."""
        _, proposals = self._load_manifest(run_id)
        return proposals

    def show_patch(self, run_id: str, patch_id: str) -> str:
        """Return the diff text for a selected patch proposal."""
        run_directory, proposals = self._load_manifest(run_id)
        proposal, _ = self._find_patch(proposals, run_id, patch_id)
        return self._read_patch_file(run_directory, proposal.patch_file)

    def apply_patch(self, run_id: str, patch_id: str, project_root: str | Path) -> Path:
        """Apply one explicitly selected patch and mark it as applied."""
        project_root_path = Path(project_root)
        if not project_root_path.exists():
            raise PatchReviewError(f"Project root does not exist: {project_root_path}")
        if not project_root_path.is_dir():
            raise PatchReviewError(f"Project root is not a directory: {project_root_path}")

        run_directory, proposals = self._load_manifest(run_id)
        proposal, proposal_index = self._find_patch(proposals, run_id, patch_id)
        if proposal.status != "proposed":
            raise PatchReviewError(
                f"Patch '{patch_id}' is not proposed; current status is '{proposal.status}'."
            )

        target_path = self._resolve_project_target(project_root_path, proposal.target_file)
        diff_text = self._read_patch_file(run_directory, proposal.patch_file)
        parsed_diff = _parse_unified_diff(diff_text)
        _validate_diff_target(parsed_diff, proposal.target_file)

        new_contents = _apply_diff_to_current_contents(target_path, parsed_diff)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_contents, encoding="utf-8")

        proposals[proposal_index] = proposal.model_copy(update={"status": "applied"})
        self._write_manifest(run_directory, proposals)
        return target_path

    def _load_manifest(self, run_id: str) -> tuple[Path, list[PatchProposal]]:
        run_id_path = Path(run_id)
        if run_id_path.is_absolute() or len(run_id_path.parts) != 1 or ".." in run_id_path.parts:
            raise PatchReviewError(f"Run ID must be a safe run directory name: {run_id}")

        run_directory = self.runs_directory / run_id_path
        if not run_directory.exists():
            raise PatchReviewError(f"Run '{run_id}' does not exist at {run_directory}.")

        manifest_path = run_directory / "patch_manifest.json"
        if not manifest_path.exists():
            raise PatchReviewError(f"Patch manifest does not exist: {manifest_path}")

        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise PatchReviewError(f"Patch manifest is invalid JSON: {manifest_path}") from error

        if not isinstance(raw_manifest, list):
            raise PatchReviewError("Patch manifest must contain a list of patch proposals.")

        try:
            proposals = [PatchProposal.model_validate(item) for item in raw_manifest]
        except ValidationError as error:
            message = f"Patch manifest contains an invalid proposal: {error}"
            raise PatchReviewError(message) from error

        return run_directory, proposals

    @staticmethod
    def _find_patch(
        proposals: list[PatchProposal],
        run_id: str,
        patch_id: str,
    ) -> tuple[PatchProposal, int]:
        for index, proposal in enumerate(proposals):
            if proposal.id == patch_id:
                return proposal, index
        raise PatchReviewError(f"Patch ID '{patch_id}' does not exist in run '{run_id}'.")

    @staticmethod
    def _read_patch_file(run_directory: Path, patch_file: str) -> str:
        relative_path = _safe_relative_path(patch_file, label="Patch file path")
        if not relative_path.parts or relative_path.parts[0] != "patches":
            raise PatchReviewError(f"Patch file path must start with patches/: {patch_file}")

        run_root = run_directory.resolve()
        patch_path = (run_root / relative_path).resolve(strict=False)
        _ensure_inside_root(patch_path, run_root, "Patch file")
        if not patch_path.exists():
            raise PatchReviewError(f"Patch file does not exist: {patch_path}")
        if not patch_path.is_file():
            raise PatchReviewError(f"Patch file is not a file: {patch_path}")
        return patch_path.read_text(encoding="utf-8")

    @staticmethod
    def _resolve_project_target(project_root: Path, target_file: str) -> Path:
        relative_path = _safe_relative_path(target_file, label="Patch target path")
        if relative_path.parts[0] == "proposed":
            raise PatchReviewError(
                f"Patch target path must not write proposal files: {target_file}"
            )
        root = project_root.resolve()
        target_path = (root / relative_path).resolve(strict=False)
        _ensure_inside_root(target_path, root, "Patch target")
        return target_path

    @staticmethod
    def _write_manifest(run_directory: Path, proposals: list[PatchProposal]) -> None:
        manifest_path = run_directory / "patch_manifest.json"
        manifest_data = [proposal.model_dump() for proposal in proposals]
        manifest_path.write_text(
            f"{json.dumps(manifest_data, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )


def _safe_relative_path(path_value: str, *, label: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        raise PatchReviewError(f"{label} must not be absolute: {path_value}")
    if not path.parts:
        raise PatchReviewError(f"{label} must not be empty.")
    if ".." in path.parts:
        raise PatchReviewError(f"{label} cannot contain traversal: {path_value}")
    return path


def _ensure_inside_root(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise PatchReviewError(f"{label} escapes project root: {path}") from error


def _validate_diff_target(parsed_diff: ParsedDiff, expected_target: str) -> None:
    expected_path = _safe_relative_path(expected_target, label="Patch target path").as_posix()
    if parsed_diff.target_path != expected_path:
        raise PatchReviewError(
            f"Patch diff target '{parsed_diff.target_path}' does not match manifest target "
            f"'{expected_path}'."
        )
    if parsed_diff.source_path != "/dev/null" and parsed_diff.source_path != expected_path:
        raise PatchReviewError(
            f"Patch diff source '{parsed_diff.source_path}' does not match manifest target "
            f"'{expected_path}'."
        )


def _parse_unified_diff(diff_text: str) -> ParsedDiff:
    lines = diff_text.splitlines()
    source_path: str | None = None
    target_path: str | None = None
    hunks: list[Hunk] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("--- "):
            source_path = _parse_diff_path(line[4:])
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ "):
                raise PatchReviewError("Patch diff is missing a target file header.")
            target_path = _parse_diff_path(lines[index][4:])
            index += 1
            continue

        if line.startswith("@@ "):
            hunk, index = _parse_hunk(lines, index)
            hunks.append(hunk)
            continue

        index += 1

    if source_path is None or target_path is None:
        raise PatchReviewError("Patch diff is missing file headers.")
    if not hunks:
        raise PatchReviewError("Patch diff does not contain any hunks.")

    return ParsedDiff(source_path=source_path, target_path=target_path, hunks=hunks)


def _parse_diff_path(header_value: str) -> str:
    path_text = header_value.split("\t", maxsplit=1)[0].strip()
    if path_text == "/dev/null":
        return path_text
    if path_text.startswith("a/") or path_text.startswith("b/"):
        path_text = path_text[2:]
    return _safe_relative_path(path_text, label="Patch diff path").as_posix()


def _parse_hunk(lines: list[str], start_index: int) -> tuple[Hunk, int]:
    header = lines[start_index]
    match = re.match(
        r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
        r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@",
        header,
    )
    if match is None:
        raise PatchReviewError(f"Patch diff has an invalid hunk header: {header}")

    old_start = int(match.group("old_start"))
    old_count = int(match.group("old_count") or "1")
    new_start = int(match.group("new_start"))
    new_count = int(match.group("new_count") or "1")
    hunk_lines: list[HunkLine] = []
    index = start_index + 1

    while index < len(lines):
        line = lines[index]
        if line.startswith("@@ "):
            break
        if line.startswith("\\"):
            index += 1
            continue
        if not line:
            raise PatchReviewError("Patch diff contains an invalid empty hunk line.")
        kind = line[0]
        if kind not in {" ", "+", "-"}:
            raise PatchReviewError(f"Patch diff contains an invalid hunk line: {line}")
        hunk_lines.append(HunkLine(kind=kind, text=line[1:]))
        index += 1

    actual_old_count = sum(1 for line in hunk_lines if line.kind != "+")
    actual_new_count = sum(1 for line in hunk_lines if line.kind != "-")
    if actual_old_count != old_count or actual_new_count != new_count:
        raise PatchReviewError(f"Patch diff hunk counts do not match header: {header}")

    return (
        Hunk(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            lines=hunk_lines,
        ),
        index,
    )


def _apply_diff_to_current_contents(target_path: Path, parsed_diff: ParsedDiff) -> str:
    original_lines = _read_target_lines(target_path)
    result_lines: list[str] = []
    cursor = 0

    for hunk in parsed_diff.hunks:
        old_index = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if old_index < cursor:
            raise PatchReviewError("Patch diff hunks overlap or are out of order.")
        if old_index > len(original_lines):
            raise PatchReviewError("Patch diff hunk starts past the end of the target file.")

        result_lines.extend(original_lines[cursor:old_index])
        cursor = old_index

        for hunk_line in hunk.lines:
            if hunk_line.kind == " ":
                _require_current_line(original_lines, cursor, hunk_line.text)
                result_lines.append(hunk_line.text)
                cursor += 1
            elif hunk_line.kind == "-":
                _require_current_line(original_lines, cursor, hunk_line.text)
                cursor += 1
            elif hunk_line.kind == "+":
                result_lines.append(hunk_line.text)
            else:
                raise PatchReviewError(f"Unsupported patch line kind: {hunk_line.kind}")

    result_lines.extend(original_lines[cursor:])
    if not result_lines:
        return ""
    return "\n".join(result_lines) + "\n"


def _read_target_lines(target_path: Path) -> list[str]:
    if not target_path.exists():
        return []
    if not target_path.is_file():
        raise PatchReviewError(f"Patch target is not a file: {target_path}")
    return target_path.read_text(encoding="utf-8").splitlines()


def _require_current_line(lines: list[str], index: int, expected: str) -> None:
    if index >= len(lines):
        raise PatchReviewError("Patch diff does not match the current target file.")
    actual = lines[index]
    if actual != expected:
        raise PatchReviewError(
            f"Patch diff does not match the current target file. "
            f"Expected '{expected}' but found '{actual}'."
        )
