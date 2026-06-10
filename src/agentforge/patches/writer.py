"""Write patch proposal artifacts for workflow runs."""

from pathlib import Path

from agentforge.patches.models import PatchProposal


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
