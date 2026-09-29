"""Span-per-node instrumentation, applied when the graph is built."""

from typing import Protocol

from triage.graphs.state import TriageState
from triage.tracing.setup import tracer
from triage.tracing.store import TICKET_ATTRIBUTE


class Node(Protocol):
    """LangGraph matches nodes structurally, on the `state` parameter name."""

    async def __call__(self, state: TriageState) -> TriageState: ...


def traced(name: str, node: Node) -> Node:
    """Wrap a node so its run, and the model calls inside it, share one span."""

    async def run(state: TriageState) -> TriageState:
        context = state["context"]
        # A resumed run reloads the context as a plain dict.
        ticket_id = getattr(context, "ticket_id", None) or context["ticket_id"]  # type: ignore[index]
        with tracer().start_as_current_span(
            f"node.{name}", attributes={TICKET_ATTRIBUTE: str(ticket_id)}
        ):
            return await node(state)

    run.__name__ = name
    return run
