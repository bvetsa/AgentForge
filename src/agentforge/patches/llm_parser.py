"""Parse LLM-authored patch proposal blocks."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from agentforge.config.schemas import AgentConfig
from agentforge.patches.models import PatchProposal

PATCH_BLOCK_RE = re.compile(r"```agentforge-patch[ \t]*\r?\n(.*?)```", re.DOTALL)
BEGIN_DIFF_MARKERS = {"---BEGIN DIFF---", "—BEGIN DIFF—"}
END_DIFF_MARKERS = {"---END DIFF---", "—END DIFF—"}


class LLMPatchParseError(ValueError):
    """Raised when an agentforge-patch block is present but invalid."""


def parse_llm_patch_proposals(
    content: str,
    *,
    agent_config: AgentConfig,
    patch_sequence: int,
) -> list[PatchProposal]:
    """Parse strict agentforge-patch fenced blocks from model output."""
    blocks = [match.group(1) for match in PATCH_BLOCK_RE.finditer(content)]
    if not blocks:
        return []

    proposals: list[PatchProposal] = []
    agent_slug = _slugify(agent_config.name)
    for index, block in enumerate(blocks, start=1):
        fields, diff = _parse_patch_block(block, block_number=index)
        target_file = fields["target_file"]
        _validate_target_file(target_file, block_number=index)
        _validate_diff_references_target(
            diff=diff,
            target_file=target_file,
            block_number=index,
        )
        proposal_id = _proposal_id(
            patch_sequence=patch_sequence,
            agent_slug=agent_slug,
            block_index=index,
        )
        proposals.append(
            PatchProposal(
                id=proposal_id,
                agent_name=agent_config.name,
                title=fields["title"],
                description=fields["description"],
                target_file=target_file,
                patch_file=f"patches/{proposal_id}.diff",
                status="proposed",
                diff=diff,
            )
        )

    return proposals


def _parse_patch_block(
    block: str,
    *,
    block_number: int,
) -> tuple[dict[str, str], str]:
    lines = block.splitlines()
    begin_index = _find_marker(lines, BEGIN_DIFF_MARKERS)
    end_index = _find_marker(lines, END_DIFF_MARKERS)
    if begin_index is None:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} is missing ---BEGIN DIFF---."
        )
    if end_index is None:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} is missing ---END DIFF---."
        )
    if end_index <= begin_index:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} has an invalid diff section."
        )

    fields = _parse_fields(lines[:begin_index], block_number=block_number)
    diff = "\n".join(lines[begin_index + 1 : end_index]).strip()
    if not diff:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} has an empty diff."
        )
    return fields, diff


def _parse_fields(lines: list[str], *, block_number: int) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        key, separator, value = stripped.partition(":")
        if not separator:
            raise LLMPatchParseError(
                f"agentforge-patch block {block_number} has invalid metadata: {line!r}."
            )
        key = key.strip()
        if key not in {"target_file", "title", "description"}:
            raise LLMPatchParseError(
                f"agentforge-patch block {block_number} has unknown metadata key: {key}."
            )
        value = value.strip()
        if not value:
            raise LLMPatchParseError(
                f"agentforge-patch block {block_number} has empty metadata: {key}."
            )
        fields[key] = value

    missing = {"target_file", "title", "description"} - fields.keys()
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} is missing metadata: {missing_text}."
        )
    return fields


def _validate_target_file(target_file: str, *, block_number: int) -> None:
    if "\\" in target_file:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} target_file must use '/' separators."
        )

    path = PurePosixPath(target_file)
    if path.is_absolute():
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} target_file must be relative."
        )
    if not path.parts or path.as_posix() in {"", "."}:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} target_file must not be empty."
        )
    if ".." in path.parts:
        raise LLMPatchParseError(
            f"agentforge-patch block {block_number} target_file cannot contain '..'."
        )


def _validate_diff_references_target(
    *,
    diff: str,
    target_file: str,
    block_number: int,
) -> None:
    expected_diff_git = f"diff --git a/{target_file} b/{target_file}"
    expected_new_file = f"+++ b/{target_file}"
    for line in diff.splitlines():
        stripped = line.strip()
        if stripped == expected_diff_git or stripped == expected_new_file:
            return
    raise LLMPatchParseError(
        f"agentforge-patch block {block_number} diff must reference {target_file!r}."
    )


def _find_marker(lines: list[str], markers: set[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() in markers:
            return index
    return None


def _proposal_id(
    *,
    patch_sequence: int,
    agent_slug: str,
    block_index: int,
) -> str:
    base_id = f"{patch_sequence:03d}-{agent_slug}"
    if block_index == 1:
        return base_id
    return f"{base_id}-{block_index}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return slug or "patch"
