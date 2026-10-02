"""What a node needs in order to speak: a callable taking one message.

The topic driving a run supplies it, bound to that run. One built without an
emitter says nothing, which is what lets an eval drive a graph with no transport.
"""

from collections.abc import Awaitable, Callable

from chanx.messages.base import BaseMessage

Emitter = Callable[[BaseMessage], Awaitable[None]]


async def silent(_event: BaseMessage) -> None:
    pass
