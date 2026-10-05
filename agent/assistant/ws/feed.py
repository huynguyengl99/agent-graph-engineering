from typing import Any

from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage

from assistant.events import Emitter
from assistant.runs import run_events


def emitter_for(topic: Topic[Any]) -> Emitter:
    """Lets a graph speak on the topic driving it, so nothing has to map a run
    back to one and a graph cannot emit onto someone else's.

    Stored before it is published, and published with that sequence - except
    for live pieces, which carry no sequence because nothing should move a
    reader's cursor past a run on a half-written sentence.
    """
    owner, name = type(topic), topic.topic

    async def emit(event: BaseMessage, *, replayable: bool = True) -> None:
        if not replayable:
            await owner.broadcast(name, event, seq=0)
            return
        seq = await run_events().append(
            name, event.action, event.model_dump(mode="json")
        )
        await owner.broadcast(name, event, seq=seq)

    return emit
