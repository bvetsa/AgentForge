"""Process provider responses into workflow outputs and artifacts."""

from dataclasses import dataclass
from typing import Any

from agentforge.config.schemas import AgentConfig
from agentforge.llm import AgentResponse
from agentforge.patches import DeterministicPatchGenerator, PatchGenerator, PatchProposal


@dataclass(frozen=True)
class ProcessedAgentResponse:
    """Workflow-ready output extracted from an agent response."""

    content: str
    patch_proposals: list[PatchProposal]
    tool_requests: list[dict[str, Any]]
    decisions: dict[str, Any] | None


class AgentResponseProcessor:
    """Convert provider responses into state updates and deterministic artifacts."""

    def __init__(self, patch_generator: PatchGenerator | None = None) -> None:
        self.patch_generator = patch_generator or DeterministicPatchGenerator()

    def process(
        self,
        agent_config: AgentConfig,
        response: AgentResponse,
        *,
        patch_sequence: int,
        patch_id_prefix: str = "",
    ) -> ProcessedAgentResponse:
        """Process one agent response after provider generation."""
        patch_proposals = self._deterministic_patch_proposals(
            agent_config=agent_config,
            patch_sequence=patch_sequence,
            patch_id_prefix=patch_id_prefix,
        )
        return ProcessedAgentResponse(
            content=response.content,
            patch_proposals=patch_proposals,
            tool_requests=list(response.tool_requests),
            decisions=response.decisions,
        )

    def _deterministic_patch_proposals(
        self,
        *,
        agent_config: AgentConfig,
        patch_sequence: int,
        patch_id_prefix: str,
    ) -> list[PatchProposal]:
        if not agent_config.produces_patches:
            return []

        proposal = self.patch_generator.create(agent_config, sequence=patch_sequence)
        if patch_id_prefix:
            proposal = _prefix_patch_proposal(proposal, patch_id_prefix)
        return [proposal]


def _prefix_patch_proposal(proposal: PatchProposal, prefix: str) -> PatchProposal:
    patch_id = f"{prefix}{proposal.id}"
    return proposal.model_copy(
        update={
            "id": patch_id,
            "patch_file": f"patches/{patch_id}.diff",
        }
    )
