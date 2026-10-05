"""The model's memory of a thread, in Pydantic AI's own messages.

A tool call is a call here, not a sentence about one. Carried on the graph's
state, so the run's checkpointer persists it.
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
    return ModelMessagesTypeAdapter.dump_json(messages).decode()


def load_messages(raw: Any) -> list[ModelMessage]:
    if not raw:
        return []
    return list(ModelMessagesTypeAdapter.validate_json(raw))


def as_messages(turns: list[Turn]) -> list[ModelMessage]:
    """Lossy: a turn cannot say which tool was called, so this only ever
    starts a memory off."""
    messages: list[ModelMessage] = []
    for turn in turns:
        if turn.role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=turn.content)]))
        else:
            messages.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
    return messages
