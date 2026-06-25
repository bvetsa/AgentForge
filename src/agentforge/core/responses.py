"""Process provider responses into workflow outputs and artifacts."""

from dataclasses import dataclass
from typing import Any

from agentforge.config.schemas import AgentConfig
from agentforge.llm import AgentResponse
from agentforge.patches import (
    DeterministicPatchGenerator,
    LLMPatchParseError,
    PatchGenerator,
    PatchProposal,
    parse_llm_patch_proposals,
)


@dataclass(frozen=True)
class ProcessedAgentResponse:
    """Workflow-ready output extracted from an agent response."""

    content: str
    patch_proposals: list[PatchProposal]
    tool_requests: list[dict[str, Any]]
    decisions: dict[str, Any] | None


class AgentResponseProcessor:
    """Convert provider responses into state updates and patch artifacts."""

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
        patch_proposals = self._patch_proposals(
            agent_config=agent_config,
            response=response,
            patch_sequence=patch_sequence,
            patch_id_prefix=patch_id_prefix,
        )
        return ProcessedAgentResponse(
            content=response.content,
            patch_proposals=patch_proposals,
            tool_requests=list(response.tool_requests),
            decisions=response.decisions,
        )

    def _patch_proposals(
        self,
        *,
        agent_config: AgentConfig,
        response: AgentResponse,
        patch_sequence: int,
        patch_id_prefix: str,
    ) -> list[PatchProposal]:
        if not agent_config.produces_patches:
            return []

        parsed_proposals = self._parse_llm_patch_proposals(
            agent_config=agent_config,
            response=response,
            patch_sequence=patch_sequence,
        )
        if parsed_proposals:
            return _prefix_patch_proposals(parsed_proposals, patch_id_prefix)
        if response.provider != "mock":
            return []

        return self._deterministic_patch_proposals(
            agent_config=agent_config,
            patch_sequence=patch_sequence,
            patch_id_prefix=patch_id_prefix,
        )

    @staticmethod
    def _parse_llm_patch_proposals(
        *,
        agent_config: AgentConfig,
        response: AgentResponse,
        patch_sequence: int,
    ) -> list[PatchProposal]:
        try:
            return parse_llm_patch_proposals(
                response.content,
                agent_config=agent_config,
                patch_sequence=patch_sequence,
            )
        except LLMPatchParseError:
            return []

    def _deterministic_patch_proposals(
        self,
        *,
        agent_config: AgentConfig,
        patch_sequence: int,
        patch_id_prefix: str,
    ) -> list[PatchProposal]:
        proposal = self.patch_generator.create(agent_config, sequence=patch_sequence)
        if patch_id_prefix:
            proposal = _prefix_patch_proposal(proposal, patch_id_prefix)
        return [proposal]


def _prefix_patch_proposals(
    proposals: list[PatchProposal],
    prefix: str,
) -> list[PatchProposal]:
    if not prefix:
        return proposals
    return [_prefix_patch_proposal(proposal, prefix) for proposal in proposals]


def _prefix_patch_proposal(proposal: PatchProposal, prefix: str) -> PatchProposal:
    patch_id = f"{prefix}{proposal.id}"
    return proposal.model_copy(
        update={
            "id": patch_id,
            "patch_file": f"patches/{patch_id}.diff",
        }
    )
