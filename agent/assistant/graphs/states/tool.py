from typing import Annotated, Any

from pydantic import BaseModel

from assistant.agents.deps import ChatContext
from assistant.graphs.states.reducers import last_wins
from assistant.outputs.tools import ToolDecision


class ToolState(BaseModel):
    """Choosing a tool, clearing it with a human, and running it."""

    context: ChatContext
    request: str = ""

    decision: ToolDecision | None = None
    # What will actually run. Separate from the proposal because a reviewer can
    # correct the arguments, and the audit trail should show both.
    tool: str = ""
    arguments: Annotated[dict[str, Any], last_wins] = {}

    # Argument names the planner made up. Not an error: the gate exists so a
    # person can fix exactly this, but they have to be told.
    unknown_arguments: list[str] = []

    approved: bool = False
    # A person changed the arguments before approving. The answer has to know:
    # told only the result, a model reads the smaller amount as a mistake and
    # advises the rep to refund the difference.
    corrected: bool = False
    cancelled: bool = False
    result: str = ""
    tool_error: str = ""
