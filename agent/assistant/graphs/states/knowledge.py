from assistant.graphs.states.base import BaseState, Knowledge


class KnowledgeState(BaseState, Knowledge):
    """The retrieval loop's own state.

    `kb_query` and `kb_snippets` are the parent's; the rest is private, so the
    parent never sees how many attempts it took.
    """

    kb_attempts: int = 0
    kb_exhausted: bool = False
