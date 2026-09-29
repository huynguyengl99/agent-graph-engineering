from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from assistant.agents import answer_agent, classifier_agent, decision_agent
from assistant.agents.deps import TicketContext
from assistant.graphs.state import TriageState
from assistant.outputs.triage import (
    Escalate,
    SearchKnowledgeBase,
    TicketAnswer,
)
from assistant.tools.knowledge_base import search_knowledge_base
from assistant.tools.reply import send_reply_to_customer
from assistant.tracing.nodes import Node, traced


def _context_of(state: TriageState) -> TicketContext:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    context = state["context"]
    return context if isinstance(context, TicketContext) else TicketContext(**context)


def _answer_of(state: TriageState) -> TicketAnswer:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    answer = state["answer"]
    return (
        answer
        if isinstance(answer, TicketAnswer)
        else TicketAnswer.model_validate(answer)
    )


async def classify(state: TriageState) -> TriageState:
    context = _context_of(state)
    result = await classifier_agent.run(context.render(), deps=context)
    return {"classification": result.output}


async def decide(state: TriageState) -> TriageState:
    context = _context_of(state)
    result = await decision_agent.run(context.render(), deps=context)
    return {"decision": result.output}


async def search_kb(state: TriageState) -> TriageState:
    decision = state["decision"]
    assert isinstance(decision, SearchKnowledgeBase)

    output = await search_knowledge_base(decision.query)
    if not output.ok:
        return {"kb_snippets": [], "tool_error": output.user_error or output.error or ""}

    return {"kb_snippets": [article.render() for article in output.result]}


async def escalate(state: TriageState) -> TriageState:
    decision = state["decision"]
    assert isinstance(decision, Escalate)
    return {
        "escalation_reason": decision.reason,
        "answer": TicketAnswer(
            content=(
                "Thanks for reaching out. I am handing this to a specialist on "
                f"our {decision.suggested_team} team, who will follow up here."
            ),
            requires_approval=False,
        ),
    }


async def respond(state: TriageState) -> TriageState:
    context = _context_of(state)
    prompt = context.render()

    snippets = state.get("kb_snippets") or []
    if snippets:
        prompt += "\n\nKnowledge base articles:\n" + "\n\n".join(snippets)

    result = await answer_agent.run(prompt, deps=context)
    # Anything the customer will read goes through a human first.
    return {"answer": result.output.model_copy(update={"requires_approval": True})}


async def await_approval(state: TriageState) -> TriageState:
    """Park the run until a human accepts, edits, or rejects the draft."""
    answer = _answer_of(state)
    decision = interrupt({"kind": "reply_approval", "draft": answer.content})

    approved = (
        bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    )
    if not approved:
        return {
            "approval_granted": False,
            "answer": answer.model_copy(
                update={"content": "The draft reply was rejected by a reviewer."}
            ),
        }

    edited = decision.get("content") if isinstance(decision, dict) else None
    return {
        "approval_granted": True,
        "answer": answer.model_copy(update={"content": edited or answer.content}),
    }


async def send_reply(state: TriageState) -> TriageState:
    """The irreversible step, reachable only once approval is granted."""
    answer = _answer_of(state)
    output = await send_reply_to_customer(
        _context_of(state).ticket_id, answer.content, approved=True
    )
    if not output.ok:
        return {"tool_error": output.user_error or output.error or ""}
    return {"delivery_receipt": str(output.result)}


def route_after_approval(state: TriageState) -> str:
    return "send_reply" if state.get("approval_granted") else END


def route_decision(state: TriageState) -> str:
    match state["decision"]:
        case SearchKnowledgeBase():
            return "search_kb"
        case Escalate():
            return "escalate"
        case _:
            return "respond"


NODES: dict[str, Node] = {
    "classify": classify,
    "decide": decide,
    "search_kb": search_kb,
    "escalate": escalate,
    "respond": respond,
    "await_approval": await_approval,
    "send_reply": send_reply,
}


def build_graph() -> StateGraph:
    graph = StateGraph(TriageState)

    # Instrumented here, so no node body carries tracing code.
    for name, node in NODES.items():
        graph.add_node(name, traced(name, node))

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "decide")
    graph.add_conditional_edges(
        "decide",
        route_decision,
        {"search_kb": "search_kb", "escalate": "escalate", "respond": "respond"},
    )
    graph.add_edge("search_kb", "respond")
    graph.add_edge("escalate", END)
    graph.add_edge("respond", "await_approval")
    graph.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {"send_reply": "send_reply", END: END},
    )
    graph.add_edge("send_reply", END)

    return graph


# Checkpoints carry our own models, so their modules must be allow-listed.
serde = JsonPlusSerializer(
    allowed_msgpack_modules=[
        ("assistant.outputs.triage", name)
        for name in (
            "Classification",
            "AnswerDirectly",
            "SearchKnowledgeBase",
            "Escalate",
            "DraftReply",
            "TicketAnswer",
        )
    ]
    + [("assistant.agents.deps", "TicketContext")]
)

# Swapping in a Postgres saver is the only change needed to survive a restart.
checkpointer = InMemorySaver(serde=serde)
triage_graph = build_graph().compile(checkpointer=checkpointer)
