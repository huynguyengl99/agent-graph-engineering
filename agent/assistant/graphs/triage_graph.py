from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import AgentConfig, AnswerAgent, ClassifierAgent, DecisionAgent
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.delivery_graph import build_delivery_graph
from assistant.graphs.feed import AnswerFeed
from assistant.graphs.knowledge_graph import build_knowledge_graph
from assistant.graphs.states import TriageState
from assistant.guardrails import screen_input
from assistant.messages.triage import (
    ClassifiedMessage,
    ClassifiedPayload,
    DecidedMessage,
    DecidedPayload,
)
from assistant.outputs.triage import (
    Escalate,
    SearchKnowledgeBase,
    TicketAnswer,
    TriageDecision,
)
from assistant.tracing.nodes import Node


def _reasoning(decision: TriageDecision) -> str:
    match decision:
        case Escalate():
            return decision.reason
        case _:
            return decision.reasoning


class TriageGraph(AnswerFeed, BaseGraph):
    """Works one ticket: file it, decide what to do, then answer or escalate.

    Retrieval and delivery are subgraphs, so this graph only holds the
    decisions. Adding a capability means a branch here and a graph of its own,
    not another `if` in a handler.
    """

    name = "triage"

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        super().__init__(config, emitter)
        self.classifier = ClassifierAgent(self.config)
        self.decider = DecisionAgent(self.config)
        self.answerer = AnswerAgent(self.config)

    async def classify(self, state: TriageState) -> TriageState:
        context = state["context"]
        # Recorded, not refused: see assistant/guardrails/input.py.
        attempts = screen_input(context.untrusted_text())
        classification = await self.classifier.run(context.render(), context)
        await self.emit(
            ClassifiedMessage(
                payload=ClassifiedPayload(
                    ticket_id=context.ticket_id,
                    category=classification.category,
                    priority=classification.priority,
                    reasoning=classification.reasoning,
                )
            )
        )
        return {
            "classification": classification,
            "guardrail_findings": attempts.rendered(),
        }

    async def decide(self, state: TriageState) -> TriageState:
        context = state["context"]
        decision = await self.decider.run(context.render(), context)
        await self.emit(
            DecidedMessage(
                payload=DecidedPayload(
                    ticket_id=context.ticket_id,
                    decision=type(decision).__name__,
                    reasoning=_reasoning(decision),
                )
            )
        )

        update: TriageState = {"decision": decision}
        if isinstance(decision, SearchKnowledgeBase):
            # The handoff into the subgraph: it searches for what the decider
            # asked for, not for the whole ticket.
            update["kb_query"] = decision.query
        return update

    async def escalate(self, state: TriageState) -> TriageState:
        decision = state["decision"]
        assert isinstance(decision, Escalate)
        answer = TicketAnswer(
            content=(
                "Thanks for reaching out. I am handing this to a specialist on "
                f"our {decision.suggested_team} team, who will follow up here."
            ),
            requires_approval=False,
        )
        await self.answered(state["context"].ticket_id, answer)
        return {"escalation_reason": decision.reason, "answer": answer}

    async def respond(self, state: TriageState) -> TriageState:
        context = state["context"]
        prompt = context.render()

        snippets = state.get("kb_snippets") or []
        if snippets:
            prompt += "\n\nKnowledge base articles:\n" + "\n\n".join(snippets)

        answer = await self.answerer.run(prompt, context)
        # Anything the customer will read goes through a human first.
        answer = answer.model_copy(update={"requires_approval": True})
        await self.answered(context.ticket_id, answer)
        return {"answer": answer}

    def route_decision(self, state: TriageState) -> str:
        match state["decision"]:
            case SearchKnowledgeBase():
                return "knowledge"
            case Escalate():
                return "escalate"
            case _:
                return "respond"

    def nodes(self) -> dict[str, Node]:
        """Only this graph's own steps. Subgraphs are added whole, in build()."""
        return {
            "classify": self.classify,
            "decide": self.decide,
            "escalate": self.escalate,
            "respond": self.respond,
        }

    def build(self) -> StateGraph[TriageState, None, TriageState, TriageState]:
        graph: StateGraph[TriageState, None, TriageState, TriageState] = StateGraph(
            TriageState
        )
        self.add_nodes(graph)

        # Compiled subgraphs go in as nodes. They share the keys they need with
        # this state, so nothing has to be mapped across the boundary.
        graph.add_node("knowledge", build_knowledge_graph(self.config))
        graph.add_node("delivery", build_delivery_graph(self.config, self.emit))

        graph.add_edge(START, "classify")
        graph.add_edge("classify", "decide")
        graph.add_conditional_edges(
            "decide",
            self.route_decision,
            {"knowledge": "knowledge", "escalate": "escalate", "respond": "respond"},
        )
        graph.add_edge("knowledge", "respond")
        graph.add_edge("escalate", END)
        graph.add_edge("respond", "delivery")
        graph.add_edge("delivery", END)

        return graph


def build_triage_graph(
    config: AgentConfig | None = None,
    saver: BaseCheckpointSaver[str] | None = None,
    emitter: Emitter = silent,
) -> CompiledStateGraph[TriageState, None, TriageState, TriageState]:
    """Compile a run's graph. Cheap, and the topology never varies; what varies
    is which model each purpose resolves to, and where its events go."""
    return TriageGraph(config, emitter).compile(saver or checkpointer())
