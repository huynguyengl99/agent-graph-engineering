from typing import Annotated, Any, TypedDict

from assistant.agents.deps import ChatContext
from assistant.outputs.tools import ToolDecision


def last_wins(_current: object, incoming: object) -> object:
    return incoming


class ToolState(TypedDict, total=False):
    """Choosing a tool, clearing it with a human, and running it."""

    context: ChatContext
    request: str

    decision: ToolDecision
    # What will actually run. Separate from the proposal because a reviewer
    # can correct the arguments, and the audit trail should show both.
    tool: str
    arguments: Annotated[dict[str, Any], last_wins]

    approved: bool
    cancelled: bool
    result: str
    tool_error: str
