from typing import Annotated, Any, TypedDict

from assistant.agents.deps import ChatContext
from assistant.outputs.chat import ChatRoute


def last_wins(_current: object, incoming: object) -> object:
    return incoming


class ChatState(TypedDict, total=False):
    """State for one turn of the rep's conversation.

    A turn, not the whole thread: the history lives on the context, and the
    checkpointer keys on the conversation.
    """

    context: ChatContext
    question: str
    route: ChatRoute
    answer: str

    # Shared with the knowledge subgraph, which is how a compiled graph can be
    # dropped in as a node here as well as in triage.
    kb_query: str
    kb_snippets: Annotated[list[str], last_wins]

    # Shared with the tool subgraph. `request` is what it plans against.
    request: str
    tool: str
    arguments: Annotated[dict[str, Any], last_wins]
    unknown_arguments: list[str]
    approved: bool
    corrected: bool
    cancelled: bool
    result: str
    tool_error: str
