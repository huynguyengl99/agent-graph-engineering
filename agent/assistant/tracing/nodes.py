"""Span-per-node instrumentation, applied when the graph is built."""

from typing import Any, Protocol

from assistant.tracing.setup import tracer
from assistant.tracing.store import RUN_ATTRIBUTE


class Node(Protocol):
    """LangGraph matches nodes structurally, on the `state` parameter name."""

    async def __call__(self, state: Any) -> Any: ...


def _run_key(state: Any) -> str:
    """What this run is filed under: a ticket for triage, a conversation for
    chat. A resumed run reloads the context as a plain dict."""
    context = state["context"]
    if isinstance(context, dict):
        return str(context.get("ticket_id") or context.get("conversation_id") or "")
    return str(getattr(context, "trace_key", ""))


def traced(name: str, node: Node) -> Node:
    """Wrap a node so its run, and the model calls inside it, share one span."""

    async def run(state: Any) -> Any:
        with tracer().start_as_current_span(
            f"node.{name}", attributes={RUN_ATTRIBUTE: _run_key(state)}
        ):
            return await node(state)

    run.__name__ = name
    return run
