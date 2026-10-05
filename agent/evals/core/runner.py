"""Run one scenario against the real graph and record what happened."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from assistant.agents import AgentConfig, Audience, Context, Ticket, Turn
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph
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
    tool: str | None = None
    parked: bool = False
    cost: RunCost = field(default_factory=RunCost)
    error: str | None = None


async def run_trial(scenario: Scenario, config: AgentConfig) -> Observation:
    """Drive the graph to wherever it stops: a gate, or a block."""
    setup_tracing()

    if scenario.audience == "team":
        return await _run_chat(scenario, config)
    return await _run_triage(scenario, config)


async def _run_chat(scenario: Scenario, config: AgentConfig) -> Observation:
    """The team's run, driven to the tool gate or to an answer."""
    conversation_id = str(uuid.uuid4())
    context = Context(
        thread_id=conversation_id,
        history=[Turn("user", turn) for turn in scenario.history],
        ticket=(
            Ticket(
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
    graph = SupportGraph(config).compile(memory_checkpointer())
    try:
        state = await graph.ainvoke(
            SupportState(context=context, question=scenario.question), config=runnable
        )
    except Exception as exc:  # a crashed run is a failed scenario, not a crashed suite
        return Observation(error=f"{type(exc).__name__}: {exc}")

    parked, tool = await _gate(graph, runnable, state)
    decision = state.get("decision")
    return Observation(
        decision=type(decision).__name__ if decision is not None else None,
        tool=tool,
        parked=parked,
        answer=getattr(state.get("answer"), "content", "") or "",
        cost=trace_store.cost(context.trace_key),
    )


async def _gate(
    graph: Any, runnable: RunnableConfig, state: Any
) -> tuple[bool, str | None]:
    """Whether the run stopped for a person, and what it was holding.

    A subgraph's writes merge only when it returns, so while parked the parent
    knows nothing: the proposal is in the interrupt, where the UI reads it too.
    """
    snapshot = await graph.aget_state(runnable)
    interrupts = [i for task in snapshot.tasks for i in task.interrupts]
    proposal: dict[str, Any] = next(
        (i.value for i in interrupts if isinstance(i.value, dict)), {}
    )
    return bool(interrupts), str(
        proposal.get("tool") or state.get("tool") or ""
    ) or None


async def _run_triage(scenario: Scenario, config: AgentConfig) -> Observation:
    ticket_id = str(uuid.uuid4())
    context = Context(
        thread_id=ticket_id,
        audience=Audience.CUSTOMER,
        ticket=Ticket(
            ticket_id=ticket_id,
            title=scenario.title,
            description=scenario.description,
        ),
        # A thread alternates, starting with the customer - which is what the
        # backend sends, and what decides whether the agent can tell its own
        # replies from theirs.
        history=[
            Turn(role="user" if i % 2 == 0 else "assistant", content=line)
            for i, line in enumerate(scenario.history)
        ],
    )
    runnable: RunnableConfig = {"configurable": {"thread_id": ticket_id}}

    graph = SupportGraph(config).compile(memory_checkpointer())
    try:
        state = await graph.ainvoke(SupportState(context=context), config=runnable)
    except Exception as exc:  # a crashed run is a failed scenario, not a crashed suite
        return Observation(error=f"{type(exc).__name__}: {exc}")

    classification = state.get("classification")
    decision = state.get("decision")
    answer = state.get("answer")
    parked, tool = await _gate(graph, runnable, state)

    return Observation(
        category=getattr(classification, "category", None),
        priority=getattr(classification, "priority", None),
        decision=type(decision).__name__ if decision is not None else None,
        tool=tool,
        parked=parked,
        used_knowledge_base=bool(state.get("kb_snippets")),
        kb_snippets=[str(s) for s in state.get("kb_snippets") or []],
        blocked=bool(state.get("reply_blocked")),
        findings=[str(f) for f in state.get("guardrail_findings") or []],
        answer=getattr(answer, "content", "") or "",
        cost=trace_store.cost(context.trace_key),
    )
