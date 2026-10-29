"""The run's root span, opened by compiling a graph rather than by its callers."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

from assistant.tracing.setup import tracer
from assistant.tracing.store import RUN_ATTRIBUTE, THREAD_ATTRIBUTE


def state_key(state: Any) -> str:
    """What a run is filed under: one question answered, whoever asked."""
    context = (
        state.get("context")
        if isinstance(state, dict)
        else getattr(state, "context", None)
    )
    return str(getattr(context, "trace_key", ""))


def _thread(config: Any) -> str:
    return str((config or {}).get("configurable", {}).get("thread_id") or "")


@contextmanager
def run_span(name: str, run_key: str, thread: str) -> Iterator[None]:
    with tracer().start_as_current_span(
        name, attributes={RUN_ATTRIBUTE: run_key, THREAD_ATTRIBUTE: thread}
    ):
        yield


class TracedRun:
    """A compiled graph that opens its run's root span however it is driven.

    Without a root each node opens its own, and one run reads as a dozen
    unrelated traces.
    """

    def __init__(self, name: str, graph: Any) -> None:
        self.name = name
        self.graph = graph

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self.graph, attribute)

    async def _opening(self, state: Any, config: Any) -> tuple[str, str]:
        """Both a first run and a resume arrive as a whole state.

        They are separate runs now, so they are separate spans, and they share
        a tree because the key comes from the ticket rather than from the run.
        The label distinguishes them for whoever reads the trace.
        """
        resuming = getattr(state, "resuming", None) or (
            state.get("resuming") if isinstance(state, dict) else None
        )
        label = "run resumed" if resuming else "run"
        return f"{self.name} {label}", state_key(state)

    async def ainvoke(self, state: Any, config: Any = None, **kwargs: Any) -> Any:
        name, key = await self._opening(state, config)
        with run_span(name, key, _thread(config)):
            return await self.graph.ainvoke(state, config=config, **kwargs)

    async def astream(
        self, state: Any, config: Any = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        name, key = await self._opening(state, config)
        # Nodes run as this is consumed, so the span outlives the call.
        with run_span(name, key, _thread(config)):
            async for chunk in self.graph.astream(state, config=config, **kwargs):
                yield chunk
