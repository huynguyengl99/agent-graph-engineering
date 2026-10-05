"""What a node needs in order to speak: a callable taking one message.

The topic driving a run supplies it, bound to that run. One built without an
emitter says nothing, which is what lets an eval drive a graph with no transport.

`replayable=False` is for the pieces of something rather than the thing: the
deltas of a reasoning being written, the tokens of an answer. The finished text
is the record and is stored; re-sending the pieces to a reader who missed them
would replay a typing animation nobody is watching any more.
"""

from typing import Protocol

from chanx.messages.base import BaseMessage


class Emitter(Protocol):
    # Positional-only, so an implementation is free to name it whatever reads
    # best at its own call site.
    async def __call__(
        self, event: BaseMessage, /, *, replayable: bool = True
    ) -> None: ...


async def silent(_event: BaseMessage, *, replayable: bool = True) -> None:
    pass
