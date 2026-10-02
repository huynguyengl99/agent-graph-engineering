"""Run one scenario against the real graph and record what happened."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from assistant.agents import AgentConfig, TicketContext
from assistant.agents.deps import ChatContext
from assistant.graphs.chat_graph import ChatGraph
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.states import ChatState, TriageState
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
    kb_snippets: list[str] = field(default_factory=list)
    blocked: bool = False
    findings: list[str] = field(default_factory=list)
    answer: str = ""
    # Chat only.
    route: str | None = None
    tool: str | None = None
    parked: bool = False
    cost: RunCost = field(default_factory=RunCost)
    error: str | None = None


async def run_trial(scenario: Scenario, config: AgentConfig) -> Observation:
    """Drive the graph to wherever it stops: a gate, or a block."""
    setup_tracing()

    if scenario.kind == "chat":
        return await _run_chat(scenario, config)
    return await _run_triage(scenario, config)


async def _run_chat(scenario: Scenario, config: AgentConfig) -> Observation:
    """The rep-facing graph, driven to the tool gate or to an answer."""
    conversation_id = str(uuid.uuid4())
    context = ChatContext(
        conversation_id=conversation_id,
        history=[("user", turn) for turn in scenario.history],
        ticket=(
            TicketContext(
                ticket_id=conversation_id,
                title=scenario.ticket,
                description=scenario.ticket,
            )
            if scenario.ticket
            else None
        ),
    )
    runnable: RunnableConfig = {"configurable": {"thread_id": conversation_id}}

    # A checkpointer of its own: the tool gate interrupts, and an eval drives
    # the graph without the service's Postgres saver.
    graph = ChatGraph(config).compile(memory_checkpointer())
    try:
        state = await graph.ainvoke(
            ChatState(context=context, question=scenario.question), config=runnable
        )
    except Exception as exc:  # a crashed run is a failed scenario, not a crashed suite
        return Observation(error=f"{type(exc).__name__}: {exc}")

    # A subgraph's writes merge only when it returns, so while parked the parent
    # knows nothing: the proposal is in the interrupt, where the UI reads it too.
    snapshot = await graph.aget_state(runnable)
    interrupts = [i for task in snapshot.tasks for i in task.interrupts]
    proposal: dict[str, Any] = next(
        (i.value for i in interrupts if isinstance(i.value, dict)), {}
    )

    route = state.get("route")
    return Observation(
        route=type(route).__name__ if route is not None else None,
        tool=str(proposal.get("tool") or state.get("tool") or "") or None,
        parked=bool(interrupts),
        answer=str(state.get("answer") or ""),
        cost=trace_store.cost(conversation_id),
    )


async def _run_triage(scenario: Scenario, config: AgentConfig) -> Observation:
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
        state = await graph.ainvoke(TriageState(context=context), config=runnable)
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
        kb_snippets=[str(s) for s in state.get("kb_snippets") or []],
        blocked=bool(state.get("reply_blocked")),
        findings=[str(f) for f in state.get("guardrail_findings") or []],
        answer=getattr(answer, "content", "") or "",
        cost=trace_store.cost(ticket_id),
    )
