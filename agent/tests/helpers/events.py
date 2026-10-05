from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from chanx.core.testing import capture_topic_broadcasts


class Recorded:
    """What a topic published, in order. Thin wrapper so assertions read as
    actions rather than as capture records."""

    def __init__(self, captured: list[Any]) -> None:
        self._captured = captured

    def actions(self) -> list[str]:
        return [record.event.action for record in self._captured]

    def of(self, action: str) -> list[Any]:
        """Every event of one action, in order."""
        return [
            record.event for record in self._captured if record.event.action == action
        ]

    def last(self, action: str) -> Any:
        return next(
            record.event
            for record in reversed(self._captured)
            if record.event.action == action
        )


@contextmanager
def recording(topic_class: Any) -> Iterator[Recorded]:
    with capture_topic_broadcasts(topic_class) as captured:
        yield Recorded(captured)
