from typing import Any

from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage

from assistant.events import Emitter


def emitter_for(topic: Topic[Any]) -> Emitter:
    """Lets a graph speak on the topic that is driving it.

    The topic already knows its own name, so nothing has to map a run back to
    one, and a graph cannot emit onto a run that is not its own.
    """
    owner, name = type(topic), topic.topic

    async def emit(event: BaseMessage) -> None:
        await owner.broadcast(name, event)

    return emit
