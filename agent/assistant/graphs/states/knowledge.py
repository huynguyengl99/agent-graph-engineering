from typing import Annotated

from pydantic import BaseModel

from assistant.agents.deps import Context
from assistant.graphs.states.reducers import last_wins


class KnowledgeState(BaseModel):
    """The retrieval loop's own state.

    `context` and `kb_snippets` are shared with the parent; the rest is private, so
    the parent never sees how many attempts it took. `context` is either parent's,
    which is why `knowledge_graph` reads it through helpers that match on type.
    """

    context: Context
    kb_snippets: Annotated[list[str], last_wins] = []

    kb_query: str = ""
    kb_attempts: int = 0
    kb_exhausted: bool = False
