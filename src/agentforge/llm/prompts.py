"""Prompt construction for agent invocations."""

from agentforge.config.schemas import AgentConfig
from agentforge.llm.base import AgentInvocation


class AgentPromptBuilder:
    """Build provider-ready prompts from agent configuration and state inputs."""

    def build(self, agent_config: AgentConfig, inputs: dict[str, str]) -> AgentInvocation:
        """Create one invocation for an agent execution step."""
        normalized_inputs = dict(inputs)
        return AgentInvocation(
            agent_name=agent_config.name,
            description=agent_config.description,
            system_prompt=agent_config.system_prompt,
            input_keys=list(agent_config.input_keys),
            output_key=agent_config.output_key,
            inputs=normalized_inputs,
            prompt=self._build_prompt(agent_config, normalized_inputs),
        )

    @staticmethod
    def _build_prompt(agent_config: AgentConfig, inputs: dict[str, str]) -> str:
        sections = [
            "# Agent",
            agent_config.name,
            "",
            "## Description",
            agent_config.description,
            "",
            "## System Prompt",
            agent_config.system_prompt,
            "",
            "## Inputs",
            "",
        ]
        for key, value in inputs.items():
            sections.extend([f"### {key}", value, ""])
        return "\n".join(sections).rstrip() + "\n"
