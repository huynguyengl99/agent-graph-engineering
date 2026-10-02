"""Span-per-node instrumentation, applied when the graph is built."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol

from assistant.tracing.setup import tracer
from assistant.tracing.store import RUN_ATTRIBUTE


class Node(Protocol):
    """LangGraph matches nodes structurally, on the `state` parameter name."""

    async def __call__(self, state: Any) -> Any: ...


def _run_key(state: Any) -> str:
    """What this run is filed under: a ticket for triage, a conversation for chat.

    Read off the state model LangGraph validated on the way in, so both contexts
    answer through `trace_key` and neither has to be unpacked here.
    """
    return str(getattr(getattr(state, "context", None), "trace_key", ""))


# What a node decided, not what it wrote. A draft reply or a prompt in a span
# would be customer text in the trace store and in whatever collector it is
# forwarded to, so only short scalars are recorded and prose is skipped by
# length.
MAX_DECISION = 60


def _decisions(update: Any) -> dict[str, str | int | float | bool]:
    """The scalar fields a node returned, for the span that ran it.

    Without these a node row says only how long it took, which is the thing
    the diagram already tells you.
    """
    if not isinstance(update, dict):
        return {}

    recorded: dict[str, str | int | float | bool] = {}
    for key, value in update.items():
        if value is None:
            continue
        if isinstance(value, bool | int | float):
            recorded[key] = value
        elif isinstance(value, str):
            # Long strings are prose. Skipped entirely rather than falling
            # through to the branch below, which recorded them as "str".
            if 0 < len(value) <= MAX_DECISION:
                recorded[key] = value
        elif not isinstance(value, dict | list | tuple | set):
            # A pydantic output like `ConsultKnowledgeBase`: the class is the
            # decision, and its fields may be prose.
            recorded[key] = type(value).__name__
    return recorded


def traced(name: str, node: Node) -> Node:
    """Wrap a node so its run, and the model calls inside it, share one span."""

    async def run(state: Any) -> Any:
        with tracer().start_as_current_span(
            f"node.{name}", attributes={RUN_ATTRIBUTE: _run_key(state)}
        ) as span:
            update = await node(state)
            for key, value in _decisions(update).items():
                span.set_attribute(key, value)
            return update

    run.__name__ = name
    return run


@contextmanager
def run_span(graph: str, run_key: str) -> Iterator[None]:
    """One span per run, so every node nests under it.

    Without this each node opens its own root and a backend shows one ticket
    as a dozen unrelated traces - the flat list of model calls this project
    exists to complain about. The in-memory view happened to hide it by
    grouping on the run key.
    """
    with tracer().start_as_current_span(
        f"{graph} run", attributes={RUN_ATTRIBUTE: run_key}
    ):
        yield
