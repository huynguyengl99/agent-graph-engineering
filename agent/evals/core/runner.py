"""Run one scenario against the real graph and record what happened."""

import uuid
from dataclasses import dataclass, field

from assistant.agents import AgentConfig, TicketContext
from assistant.graphs.triage_graph import TriageGraph
from assistant.tracing import setup_tracing, trace_store
from assistant.tracing.cost import RunCost
from langchain_core.runnables import RunnableConfig

from evals.core.scenario import Scenario


@dataclass(slots=True)
class Observation:
    """One trial's outcome, in the terms scenarios are written in."""

    category: str | None = None
    priority: str | None = None
    decision: str | None = None
    used_knowledge_base: bool = False
    blocked: bool = False
    findings: list[str] = field(default_factory=list)
    answer: str = ""
    cost: RunCost = field(default_factory=RunCost)
    error: str | None = None


async def run_trial(scenario: Scenario, config: AgentConfig) -> Observation:
    """Drive the graph to wherever it stops: the approval gate, or a block."""
    setup_tracing()

    ticket_id = str(uuid.uuid4())
    context = TicketContext(
        ticket_id=ticket_id,
        title=scenario.title,
        description=scenario.description,
        history=list(scenario.history),
    )
    runnable: RunnableConfig = {"configurable": {"thread_id": ticket_id}}

    graph = TriageGraph(config).build().compile()
    try:
        state = await graph.ainvoke({"context": context}, config=runnable)
    except Exception as exc:  # a crashed run is a failed scenario, not a crashed suite
        return Observation(error=f"{type(exc).__name__}: {exc}")

    classification = state.get("classification")
    decision = state.get("decision")
    answer = state.get("answer")

    return Observation(
        category=getattr(classification, "category", None),
        priority=getattr(classification, "priority", None),
        decision=type(decision).__name__ if decision is not None else None,
        used_knowledge_base=bool(state.get("kb_snippets")),
        blocked=bool(state.get("reply_blocked")),
        findings=[str(f) for f in state.get("guardrail_findings") or []],
        answer=getattr(answer, "content", "") or "",
        cost=trace_store.cost(ticket_id),
    )
