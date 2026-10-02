"""The replay half of `assistant.runs`, for a topic to mix in."""

from typing import Any

import structlog
from chanx.core.decorators import ws_handler

from assistant.messages.runs import ReplayRequestMessage
from assistant.runs import run_events

logger = structlog.get_logger(__name__)


class Replays:
    """Answers `replay_request` with what this run already said, on the asking
    connection rather than broadcast."""

    @ws_handler(
        summary="Re-send events a subscriber missed",
        description=(
            "Answers with every event this run published after the given "
            "sequence, in order, on the asking connection only."
        ),
    )
    async def handle_replay_request(self: Any, message: ReplayRequestMessage) -> None:
        missed = await run_events().since(self.topic, message.payload.since)
        if not missed:
            return
        await logger.ainfo(
            "runs.replayed",
            topic=self.topic,
            since=message.payload.since,
            count=len(missed),
        )
        for stored in missed:
            await self.consumer.send_topic_json(self.topic, stored.event)
