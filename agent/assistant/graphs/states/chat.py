from typing import TypedDict

from assistant.agents.deps import ChatContext


class ChatState(TypedDict, total=False):
    """State for one turn of the rep's conversation.

    A turn, not the whole thread: the history lives on the context, and the
    checkpointer keys on the conversation.
    """

    context: ChatContext
    question: str
    answer: str
