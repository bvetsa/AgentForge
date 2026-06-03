"""Pydantic schemas for AgentForge YAML files."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentConfig(BaseModel):
    """Configuration for one specialist agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    allowed_tools: list[str]
    input_keys: list[str]
    output_key: str = Field(min_length=1)

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def validate_allowed_tools(cls, value: Any) -> Any:
        """Ensure allowed tools are declared as a list of strings."""
        if not isinstance(value, list) or not all(isinstance(tool, str) for tool in value):
            raise ValueError("allowed_tools must be a list of strings")
        return value


class WorkflowConfig(BaseModel):
    """Configuration for a sequential workflow."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    agents: list[str] = Field(min_length=1)
