"""What a node needs in order to speak: a callable taking one message."""

from typing import Protocol

from chanx.messages.base import BaseMessage


class Emitter(Protocol):
    # Positional-only, so an implementation can name it whatever reads best.
    async def __call__(
        self, event: BaseMessage, /, *, replayable: bool = True
    ) -> None: ...


async def silent(_event: BaseMessage, *, replayable: bool = True) -> None:
    pass
