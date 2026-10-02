from typing import Any

from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage

from assistant.events import Emitter
from assistant.runs import run_events


def emitter_for(topic: Topic[Any]) -> Emitter:
    """Lets a graph speak on the topic driving it, so nothing has to map a run
    back to one and a graph cannot emit onto someone else's.

    Stored before it is published, and published with that sequence.
    """
    owner, name = type(topic), topic.topic

    async def emit(event: BaseMessage) -> None:
        seq = await run_events().append(
            name, event.action, event.model_dump(mode="json")
        )
        await owner.broadcast(name, event, seq=seq)

    return emit
