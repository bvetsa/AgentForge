"""Deterministic mock patch proposal generation for local tests and examples."""

import re
from collections.abc import Sequence
from typing import Protocol

from agentforge.config.schemas import AgentConfig
from agentforge.patches.models import PatchProposal


class PatchGenerator(Protocol):
    """Creates patch proposal artifacts for patch-producing agents."""

    def create(self, agent_config: AgentConfig, sequence: int) -> PatchProposal:
        """Create one patch proposal for an agent step."""


class DeterministicPatchGenerator:
    """Create deterministic sample-project patches without choosing files intelligently.

    This is temporary mock behavior for Phase 3 and Phase 4 infrastructure tests. The target
    list is deliberately sample-project-specific; it is not an architectural rule that maps
    agent roles to files. Future generators should use real model output and project context.
    """

    DEFAULT_SAMPLE_PROJECT_TARGETS = (
        "src/models.py",
        "src/app.py",
        "tests/test_app.py",
    )

    def __init__(
        self,
        sample_project_targets: Sequence[str] = DEFAULT_SAMPLE_PROJECT_TARGETS,
    ) -> None:
        if not sample_project_targets:
            raise ValueError("DeterministicPatchGenerator requires at least one target file.")
        self.sample_project_targets = tuple(sample_project_targets)

    def create(self, agent_config: AgentConfig, sequence: int) -> PatchProposal:
        """Create a deterministic placeholder patch proposal for an agent."""
        slug = _slugify(agent_config.name)
        proposal_id = f"{sequence:03d}-{slug}"
        target_file = self._target_file_for_sequence(sequence)
        patch_file = f"patches/{proposal_id}.diff"
        title = f"Mock patch proposal from {agent_config.name}"
        description = (
            "Deterministic Phase 3 patch proposal artifact. "
            "This mock diff exists to exercise human review and patch application."
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

    def _target_file_for_sequence(self, sequence: int) -> str:
        index = (sequence - 1) % len(self.sample_project_targets)
        return self.sample_project_targets[index]


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
            "+# Applied only after explicit human approval.",
        ]
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return slug or "patch"
