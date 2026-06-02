"""Workflow representation and loading."""

from dataclasses import dataclass
from pathlib import Path

from agentforge.config.loader import (
    load_agent_config,
    load_workflow_config,
    resolve_agent_path,
)
from agentforge.config.schemas import WorkflowConfig
from agentforge.core.agent import Agent


@dataclass(frozen=True)
class Workflow:
    """An ordered sequence of configured agents."""

    config: WorkflowConfig
    agents: list[Agent]

    @classmethod
    def from_file(cls, workflow_path: str | Path) -> "Workflow":
        path = Path(workflow_path)
        config = load_workflow_config(path)
        agents = [
            Agent(load_agent_config(resolve_agent_path(path, agent_path)))
            for agent_path in config.agents
        ]
        return cls(config=config, agents=agents)
