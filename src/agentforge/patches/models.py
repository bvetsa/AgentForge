"""Models for reviewable patch proposal artifacts."""

from pydantic import BaseModel, ConfigDict, Field


class PatchProposal(BaseModel):
    """A proposed code change saved as an artifact, not applied to source files."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target_file: str = Field(min_length=1)
    patch_file: str = Field(min_length=1)
    status: str = Field(min_length=1)
    diff: str = Field(min_length=1)
