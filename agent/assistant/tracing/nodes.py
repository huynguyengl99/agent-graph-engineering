"""Span-per-node instrumentation, applied when the graph is built."""

import functools
import json
from typing import Any, Protocol

from langgraph.types import Command

from assistant.tracing.runs import state_key
from assistant.tracing.setup import tracer
from assistant.tracing.store import RUN_ATTRIBUTE


class Node(Protocol):
    """LangGraph matches nodes structurally, on the `state` parameter name."""

    async def __call__(self, state: Any) -> Any: ...


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


STATE_IN = "graph.state"
STATE_UPDATE = "graph.state_update"
# Where the node sent the run. A node that returns a `Command` carries its own
# routing, so the span can say what the diagram only says in general.
GOTO = "graph.goto"


def _as_json(value: Any) -> str:
    """Whole, not summarised. A run is a sequence of state changes, and a state
    cut to fit an attribute answers nothing."""
    try:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def traced(name: str, node: Node) -> Node:
    """Wrap a node so its run, and the model calls inside it, share one span.

    The wrapper carries the wrapped node's annotations. LangGraph reads a
    node's return type to learn where a `Command` can send the run, so a
    wrapper that dropped them left the graph with almost no edges: it still ran,
    because `Command` routes at runtime, but the diagram showed a node with
    nothing after it and `xray` had no subgraph to expand.
    """

    async def run(state: Any) -> Any:
        with tracer().start_as_current_span(
            f"node.{name}", attributes={RUN_ATTRIBUTE: state_key(state)}
        ) as span:
            span.set_attribute(STATE_IN, _as_json(state))
            outcome = await node(state)

            # A node that routes itself returns the update wrapped in where it
            # is going. Recording the wrapper would lose every decision in it.
            written = outcome
            if isinstance(outcome, Command):
                span.set_attribute(GOTO, str(outcome.goto))
                written = outcome.update

            span.set_attribute(STATE_UPDATE, _as_json(written))
            for key, value in _decisions(written).items():
                span.set_attribute(key, value)
            return outcome

    functools.update_wrapper(run, node)
    # After the copy: the span and the node key are this name, not the method's.
    run.__name__ = name
    return run
