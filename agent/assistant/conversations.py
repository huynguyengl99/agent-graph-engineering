"""The model's memory of a thread, in Pydantic AI's own messages.

A tool call is a call here, not a sentence about one. Carried on the graph's
state, which goes back to the caller when the run ends and comes in again
with the next question.
"""

from typing import Any

import structlog
from pydantic import ValidationError
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


logger = structlog.get_logger(__name__)


def load_messages(raw: Any) -> list[ModelMessage]:
    """A cache over the record, so an unreadable one is dropped, not raised.

    The blob is written by the model library and comes back on every turn. A
    thread carrying one this version cannot parse, after a library upgrade or
    a bad write, would raise here on every turn and never recover, because the
    same blob is sent again next time. What is lost is the shape of past tool
    calls; the conversation itself is in the record the backend sends.
    """
    if not raw:
        return []
    try:
        return list(ModelMessagesTypeAdapter.validate_json(raw))
    except ValidationError:
        logger.warning("conversations.unreadable_memory", length=len(raw))
        return []


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
