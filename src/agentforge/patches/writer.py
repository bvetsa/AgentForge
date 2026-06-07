"""Write patch proposal artifacts for workflow runs."""

import re
from pathlib import Path

from agentforge.config.schemas import AgentConfig
from agentforge.patches.models import PatchProposal


def create_mock_patch_proposal(agent_config: AgentConfig, sequence: int) -> PatchProposal:
    """Create a deterministic placeholder patch proposal for an agent."""
    slug = _slugify(agent_config.name)
    proposal_id = f"{sequence:03d}-{slug}"
    target_file = f"proposed/{slug}.txt"
    patch_file = f"patches/{proposal_id}.diff"
    title = f"Mock patch proposal from {agent_config.name}"
    description = (
        "Deterministic Phase 3 patch proposal artifact. "
        "This diff is saved for human review and is not applied."
    )
    diff = _build_mock_diff(
        agent_name=agent_config.name,
        description=agent_config.description,
        output_key=agent_config.output_key,
        target_file=target_file,
        title=title,
    )

    return PatchProposal(
        id=proposal_id,
        agent_name=agent_config.name,
        title=title,
        description=description,
        target_file=target_file,
        patch_file=patch_file,
        status="proposed",
        diff=diff,
    )


class PatchProposalWriter:
    """Persist patch proposals beneath a run directory."""

    def write(self, run_directory: Path, patch_proposals: list[PatchProposal]) -> None:
        """Write each proposal's diff file under the run's patches directory."""
        patches_directory = run_directory / "patches"
        patches_directory.mkdir(parents=True, exist_ok=True)

        for proposal in patch_proposals:
            patch_path = self._resolve_patch_path(run_directory, proposal.patch_file)
            patch_path.parent.mkdir(parents=True, exist_ok=True)
            patch_path.write_text(f"{proposal.diff}\n", encoding="utf-8")

    @staticmethod
    def _resolve_patch_path(run_directory: Path, patch_file: str) -> Path:
        relative_path = Path(patch_file)
        if relative_path.is_absolute():
            raise ValueError(f"Patch file path must be relative: {patch_file}")
        if not relative_path.parts or relative_path.parts[0] != "patches":
            raise ValueError(f"Patch file path must start with patches/: {patch_file}")
        if ".." in relative_path.parts:
            raise ValueError(f"Patch file path cannot contain traversal: {patch_file}")
        return run_directory / relative_path


def _build_mock_diff(
    *,
    agent_name: str,
    description: str,
    output_key: str,
    target_file: str,
    title: str,
) -> str:
    return "\n".join(
        [
            f"diff --git a/{target_file} b/{target_file}",
            f"--- a/{target_file}",
            f"+++ b/{target_file}",
            "@@ -0,0 +1,5 @@",
            f"+# {title}",
            f"+# Agent: {agent_name}",
            f"+# Role: {description}",
            f"+# Output key: {output_key}",
            "+# Artifact only: this patch has not been applied.",
        ]
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return slug or "patch"
