from typing import Any

from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage

from assistant.events import Emitter
from assistant.runs import run_events


def emitter_for(topic: Topic[Any]) -> Emitter:
    """Lets a graph speak on the topic driving it."""
    owner, name = type(topic), topic.topic

    async def emit(event: BaseMessage, *, replayable: bool = True) -> None:
        # No sequence: a cursor must not move past a run on a half-written piece.
        if not replayable:
            await owner.broadcast(name, event, seq=0)
            return
        seq = await run_events().append(
            name, event.action, event.model_dump(mode="json")
        )
        await owner.broadcast(name, event, seq=seq)

    return emit
