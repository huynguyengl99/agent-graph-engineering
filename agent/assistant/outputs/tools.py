from typing import Any

from pydantic import BaseModel, Field


class ToolProposal(BaseModel):
    """A tool the assistant wants to run, and what it would pass."""

    tool: str = Field(description="The tool id, exactly as listed.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments by name."
    )
    reasoning: str = Field(description="Why this tool, in one sentence.")


class NoToolNeeded(BaseModel):
    """Nothing to run: the question is answerable as it stands."""

    reasoning: str = Field(description="Why no tool applies.")


# What the planner returns. A tool that is not in the registry is rejected
# before anything runs, so this union is a request, never a command.
ToolDecision = ToolProposal | NoToolNeeded
