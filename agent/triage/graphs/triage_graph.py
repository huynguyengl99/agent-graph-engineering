from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from triage.agents.triage_agents import (
    answer_agent,
    classifier_agent,
    decision_agent,
)
from triage.graphs.state import TriageState
from triage.outputs.triage import (
    AnswerDirectly,
    DraftReply,
    Escalate,
    SearchKnowledgeBase,
    TicketAnswer,
)
from triage.tools.knowledge_base import search_knowledge_base
from triage.tools.reply import send_reply_to_customer
from triage.tracing import TICKET_ATTRIBUTE, tracer


def _node_span(name: str, state: TriageState):
    """One span per node, tagged with the ticket.

    Pydantic AI emits its own spans for each model call, so they nest inside
    whichever node opened this one. That nesting is the whole point: the trace
    shows the route taken, not just a flat list of completions.
    """
    context = state["context"]
    ticket_id = getattr(context, "ticket_id", None) or context["ticket_id"]
    return tracer().start_as_current_span(
        f"node.{name}", attributes={TICKET_ATTRIBUTE: str(ticket_id)}
    )


async def classify(state: TriageState) -> TriageState:
    with _node_span("classify", state):
        context = state["context"]
        result = await classifier_agent.run(context.render(), deps=context)
        return {"classification": result.output}


async def decide(state: TriageState) -> TriageState:
    with _node_span("decide", state) as span:
        context = state["context"]
        result = await decision_agent.run(context.render(), deps=context)
        span.set_attribute("triage.decision", type(result.output).__name__)
        return {"decision": result.output}


async def search_kb(state: TriageState) -> TriageState:
    with _node_span("search_kb", state) as span:
        decision = state["decision"]
        assert isinstance(decision, SearchKnowledgeBase)
        span.set_attribute("triage.query", decision.query)

        # Through the wrapper, so a tool failure arrives as a typed ToolOutput
        # rather than an exception unwinding the graph.
        output = await search_knowledge_base(decision.query)
        if not output.ok:
            span.set_attribute("triage.tool_error", output.error_type or "")
            return {
                "kb_snippets": [],
                "tool_error": output.user_error or output.error,
            }

        span.set_attribute("triage.articles", len(output.result))
        return {"kb_snippets": [article.render() for article in output.result]}


async def escalate(state: TriageState) -> TriageState:
    with _node_span("escalate", state):
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
    with _node_span("respond", state) as span:
        context = state["context"]
        prompt = context.render()

        snippets = state.get("kb_snippets") or []
        if snippets:
            prompt += "\n\nKnowledge base articles:\n" + "\n\n".join(snippets)
        span.set_attribute("triage.grounded", bool(snippets))

        result = await answer_agent.run(prompt, deps=context)
        answer = result.output
        # Anything the customer will read goes through a human first.
        return {"answer": answer.model_copy(update={"requires_approval": True})}


def _answer_of(state: TriageState) -> TicketAnswer:
    """Re-validate the answer after a checkpoint round-trip.

    Resuming an interrupt reloads state through the serializer, which hands
    pydantic models back as plain dicts. Everything downstream expects the
    model, so normalise once here rather than guarding at each use.
    """
    answer = state["answer"]
    return (
        answer
        if isinstance(answer, TicketAnswer)
        else TicketAnswer.model_validate(answer)
    )


async def await_approval(state: TriageState) -> TriageState:
    """Pause the run until a human accepts or rejects the draft.

    `interrupt()` persists the graph to the checkpointer and raises out of the
    run. The resume arrives later, possibly on a different socket, and LangGraph
    replays this node with the decision as the return value.
    """
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
    """The irreversible step. Only reachable once approval has been granted."""
    with _node_span("send_reply", state) as span:
        answer = _answer_of(state)
        context = state["context"]
        ticket_id = (
            context.ticket_id if hasattr(context, "ticket_id") else context["ticket_id"]
        )
        output = await send_reply_to_customer(ticket_id, answer.content, approved=True)
        if not output.ok:
            span.set_attribute("triage.tool_error", output.error_type or "")
            return {"tool_error": output.user_error or output.error}
        return {"delivery_receipt": str(output.result)}


def route_after_approval(state: TriageState) -> str:
    return "send_reply" if state.get("approval_granted") else END


def route_decision(state: TriageState) -> str:
    match state["decision"]:
        case SearchKnowledgeBase():
            return "search_kb"
        case Escalate():
            return "escalate"
        case AnswerDirectly() | DraftReply():
            return "respond"
        case _:
            return "respond"


def build_graph() -> StateGraph:
    graph = StateGraph(TriageState)

    graph.add_node("classify", classify)
    graph.add_node("decide", decide)
    graph.add_node("search_kb", search_kb)
    graph.add_node("escalate", escalate)
    graph.add_node("respond", respond)
    graph.add_node("await_approval", await_approval)
    graph.add_node("send_reply", send_reply)

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


# Checkpoints carry our own pydantic models, so the modules holding them must be
# allow-listed for deserialization. Left implicit this only warns today, but
# LangGraph will start refusing it.
serde = JsonPlusSerializer(
    allowed_msgpack_modules=[
        ("triage.outputs.triage", name)
        for name in (
            "Classification",
            "AnswerDirectly",
            "SearchKnowledgeBase",
            "Escalate",
            "DraftReply",
            "TicketAnswer",
        )
    ]
    + [("triage.agents.triage_agents", "TicketContext")]
)

# In-memory checkpointing is enough to pause and resume within one process.
# Swapping in a Postgres saver is the only change needed to survive a restart.
checkpointer = InMemorySaver(serde=serde)
triage_graph = build_graph().compile(checkpointer=checkpointer)
