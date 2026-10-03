"""The run's root span, opened by compiling a graph rather than by its callers."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

from assistant.tracing.setup import tracer
from assistant.tracing.store import RUN_ATTRIBUTE


def state_key(state: Any) -> str:
    """What a run is filed under: a ticket for triage, a conversation for chat.

    Both contexts answer through `trace_key`, so neither has to be unpacked
    here. Dicts are accepted because LangGraph validates state on the way in
    and a caller may hand it one.
    """
    context = (
        state.get("context")
        if isinstance(state, dict)
        else getattr(state, "context", None)
    )
    return str(getattr(context, "trace_key", ""))


def _run_key(state: Any, config: Any) -> str:
    # A resume carries a `Command`, not a state, so the thread is the only key
    # that survives the park.
    thread = (config or {}).get("configurable", {}).get("thread_id")
    return str(thread) if thread else state_key(state)


@contextmanager
def run_span(graph: str, run_key: str) -> Iterator[None]:
    with tracer().start_as_current_span(
        f"{graph} run", attributes={RUN_ATTRIBUTE: run_key}
    ):
        yield


class TracedRun:
    """A compiled graph that opens its run's root span however it is driven.

    Without a root each node opens its own, and one ticket reads as a dozen
    unrelated traces - the flat list this project exists to complain about.
    It lives here rather than at the call sites because the eval runner was a
    call site, and the span it forgot showed up in the console as a run named
    `node.classify`.
    """

    def __init__(self, name: str, graph: Any) -> None:
        self.name = name
        self.graph = graph

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self.graph, attribute)

    async def ainvoke(self, state: Any, config: Any = None, **kwargs: Any) -> Any:
        with run_span(self.name, _run_key(state, config)):
            return await self.graph.ainvoke(state, config=config, **kwargs)

    async def astream(
        self, state: Any, config: Any = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        # The nodes run as this is consumed, so the span has to stay open
        # across the yields rather than wrap the call that returns the stream.
        with run_span(self.name, _run_key(state, config)):
            async for chunk in self.graph.astream(state, config=config, **kwargs):
                yield chunk
