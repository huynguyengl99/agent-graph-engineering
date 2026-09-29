from typing import Annotated, TypedDict

from assistant.agents.deps import TicketContext


def last_wins(_current: object, incoming: object) -> object:
    return incoming


class KnowledgeState(TypedDict, total=False):
    """The retrieval loop's own state.

    `context` and `kb_snippets` are shared with the parent, which is how a
    compiled subgraph can be dropped in as a node. Everything else is private
    to the loop: the parent never sees how many attempts it took.
    """

    context: TicketContext
    kb_snippets: Annotated[list[str], last_wins]

    kb_query: str
    kb_attempts: int
    kb_exhausted: bool
