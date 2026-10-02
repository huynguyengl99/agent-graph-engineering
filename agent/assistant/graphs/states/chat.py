from typing import Annotated, Any

from pydantic import BaseModel

from assistant.agents.deps import ChatContext
from assistant.graphs.states.reducers import last_wins
from assistant.outputs.chat import ChatRoute


class ChatState(BaseModel):
    """State for one turn of the rep's conversation.

    A turn, not the whole thread. Everything but the context defaults, so a fresh
    instance is what clears the last turn's tool result.
    """

    context: ChatContext
    question: str = ""
    route: ChatRoute | None = None
    answer: str = ""

    # Shared with the knowledge subgraph, which is how a compiled graph can be
    # dropped in as a node here as well as in triage.
    kb_query: str = ""
    kb_snippets: Annotated[list[str], last_wins] = []

    # Shared with the tool subgraph. `request` is what it plans against.
    request: str = ""
    tool: str = ""
    arguments: Annotated[dict[str, Any], last_wins] = {}
    unknown_arguments: list[str] = []
    approved: bool = False
    corrected: bool = False
    cancelled: bool = False
    result: str = ""
    tool_error: str = ""
