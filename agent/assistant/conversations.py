"""The model's memory of a thread, in Pydantic AI's own messages.

The backend's rows are the record a person reads. This is what the model was
actually told, which is a different thing: a tool call is a call here, not a
sentence about one.

It is carried on the graph's state and persisted by the checkpointer the run
already has. It used to live in a table of its own, behind a process-wide
singleton, written in one place and the checkpoint in another - two durable
copies of one thread that a crash between the writes could leave disagreeing,
and no way to rebuild either from the other.
"""

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from assistant.agents.deps import Turn


def dump_messages(messages: list[ModelMessage]) -> str:
    """Their own adapter writes it: that schema is the library's, not ours."""
    return ModelMessagesTypeAdapter.dump_json(messages).decode()


def load_messages(raw: Any) -> list[ModelMessage]:
    if not raw:
        return []
    return list(ModelMessagesTypeAdapter.validate_json(raw))


def as_messages(turns: list[Turn]) -> list[ModelMessage]:
    """The thread as model messages. Lossy - a turn cannot say which tool was
    called - so it only ever starts a memory off, never replaces one."""
    messages: list[ModelMessage] = []
    for turn in turns:
        if turn.role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=turn.content)]))
        else:
            messages.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
    return messages
