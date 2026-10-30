"""The publishing half of `assistant.runs`, for a topic to mix in."""

from typing import Any

from chanx.messages.base import BaseMessage


class Publishes:
    """Says a thing on this topic, and records it in the same call.

    One call, so an event cannot reach a browser while missing from the
    replay a reconnect asks for. `publish` is a bound method, which is all an
    `Emitter` is, so a graph is handed `self.publish` and can speak without
    knowing a socket exists.
    """

    topic: str

    async def publish(self, event: BaseMessage, /) -> None:
        from assistant.runs import run_events

        # A piece of something still being written gets no sequence: the
        # cursor must not move past a run on half a sentence.
        seq = (
            await run_events().append(
                self.topic, event.action, event.model_dump(mode="json")
            )
            if getattr(event, "replayable", True)
            else 0
        )
        await type(self).broadcast(self.topic, event, seq=seq)  # type: ignore[attr-defined]

    broadcast: Any
