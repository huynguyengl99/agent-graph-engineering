from typing import Any

from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage

from assistant.runs import run_events


class TopicFeed:
    """Where a graph's events go: out on the topic, and into the replay log.

    Handed to a graph rather than reached for, so a node can say something
    without knowing a socket exists and every graph test runs without one.
    Recording is the same call as publishing, so an event cannot reach a
    browser and be missing from the replay a reconnect asks for.
    """

    def __init__(self, topic: Topic[Any]) -> None:
        self.owner, self.name = type(topic), topic.topic

    async def __call__(self, event: BaseMessage) -> None:
        # A piece of something still being written gets no sequence: the
        # cursor must not move past a run on half a sentence.
        seq = (
            await run_events().append(
                self.name, event.action, event.model_dump(mode="json")
            )
            if getattr(event, "replayable", True)
            else 0
        )
        await self.owner.broadcast(self.name, event, seq=seq)
