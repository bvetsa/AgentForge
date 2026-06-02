"""Pydantic schemas for AgentForge YAML files."""

from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    """Configuration for one specialist agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    allowed_tools: list[str]
    input_keys: list[str]
    output_key: str = Field(min_length=1)


class WorkflowConfig(BaseModel):
    """Configuration for a sequential workflow."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    agents: list[str] = Field(min_length=1)
