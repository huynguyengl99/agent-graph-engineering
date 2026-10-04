from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import (
    AgentConfig,
    AnswerAgent,
    Audience,
    ClassifierAgent,
    Context,
    CustomerDecisionAgent,
    TeamDecisionAgent,
)
from assistant.agents.chat import TeamAgent
from assistant.conversations import history
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.delivery_graph import build_delivery_graph
from assistant.graphs.feed import AnswerFeed
from assistant.graphs.knowledge_graph import build_knowledge_graph
from assistant.graphs.states import SupportState, Update
from assistant.graphs.tool_graph import build_tool_graph
from assistant.guardrails import screen_input
from assistant.messages.support import (
    ChatCompleteMessage,
    ChatCompletePayload,
    ClassifiedMessage,
    ClassifiedPayload,
    DecidedMessage,
    DecidedPayload,
    ToolRanMessage,
    ToolRanPayload,
)
from assistant.outputs.support import (
    Decision,
    Escalate,
    RunTool,
    SearchKnowledgeBase,
    TicketAnswer,
)
from assistant.tracing.nodes import Node


def _reasoning(decision: Decision) -> str:
    return decision.reason if isinstance(decision, Escalate) else decision.reasoning


class SupportGraph(AnswerFeed, BaseGraph):
    """One message on a ticket, worked to an answer.

    Who the answer is for is a field on the context, not a second graph: it
    decides whether the ticket is graded, which capabilities the decider is
    offered, and whether the reply goes out through the delivery gate.
    """

    name = "support"

    @classmethod
    def thread_for(cls, context: Context) -> str:
        """A customer's run and the team's run about one ticket are two threads,
        so the audience is part of the key as well as the ticket."""
        return cls.thread(f"{context.audience}:{context.thread_id}")

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        super().__init__(config, emitter)
        self.classifier = ClassifierAgent(self.config)
        self.deciders = {
            Audience.CUSTOMER: CustomerDecisionAgent(self.config),
            Audience.TEAM: TeamDecisionAgent(self.config),
        }
        self.answerer = AnswerAgent(self.config)
        self.team = TeamAgent(self.config)

    async def classify(self, state: SupportState) -> Update:
        context = state.context
        # Recorded, not refused: see assistant/guardrails/input.py.
        attempts = screen_input(context.untrusted_text())
        classification = await self.reason(
            "classify", self.classifier, context.render(with_history=True), context
        )
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

    async def decide(self, state: SupportState) -> Update:
        context = state.context
        prompt = context.render(state.question, with_history=context.for_customer)

        decision = await self.reason(
            "decide",
            self.deciders[context.audience],
            prompt,
            context,
            await self._history(state) if state.question else None,
        )
        await self.emit(
            DecidedMessage(
                payload=DecidedPayload(
                    ticket_id=context.ticket_id,
                    decision=type(decision).__name__,
                    reasoning=_reasoning(decision),
                )
            )
        )

        update: Update = {"decision": decision}
        if isinstance(decision, SearchKnowledgeBase):
            # The handoff into the subgraph: it searches for what the decider
            # asked for, not for the whole ticket.
            update["kb_query"] = decision.query
        elif isinstance(decision, RunTool):
            # The tool subgraph plans against the asker's own words.
            update["request"] = state.question or context.render(with_history=True)
        return update

    async def escalate(self, state: SupportState) -> Update:
        decision = state.decision
        team = getattr(decision, "suggested_team", "general")
        reason = getattr(decision, "reason", None) or getattr(decision, "reasoning", "")
        answer = TicketAnswer(
            content=(
                "Thanks for reaching out. I am handing this to a specialist on "
                f"our {team} team, who will follow up here."
            ),
            requires_approval=False,
        )
        await self.answered(state.context.ticket_id, answer)
        return {"escalation_reason": reason, "answer": answer}

    async def report_tool(self, state: SupportState) -> Update:
        """What ran, before the model turns it into prose."""
        await self.emit(
            ToolRanMessage(
                payload=ToolRanPayload(
                    conversation_id=state.context.thread_id,
                    tool=state.tool or "",
                    arguments=state.arguments or {},
                    result=state.result or "",
                    error=state.tool_error or "",
                    cancelled=bool(state.cancelled),
                )
            )
        )
        return {}

    async def respond(self, state: SupportState) -> Update:
        """The one node both audiences end at, writing for whoever is reading."""
        if state.context.for_customer:
            return await self._reply_to_customer(state)
        return await self._answer_the_team(state)

    async def _reply_to_customer(self, state: SupportState) -> Update:
        context = state.context
        answer = await self.answerer.run(self._prompt(state), context)
        # Anything the customer will read goes through a human first.
        answer = answer.model_copy(update={"requires_approval": True})
        await self.answered(context.ticket_id, answer)
        return {"answer": answer}

    async def _answer_the_team(self, state: SupportState) -> Update:
        context = state.context
        # LangGraph's custom stream channel: deltas leave the node as they are
        # produced rather than being returned in one block at the end.
        writer = get_stream_writer()

        parts: list[str] = []
        async for delta in self.team.stream(
            self._prompt(state), context, await self._history(state)
        ):
            parts.append(delta)
            writer({"kind": "answer", "delta": delta})

        answer = "".join(parts)
        # Everything this turn saw, the model's own reply included, so the next
        # turn reads its actions as the calls they were rather than as prose.
        await history().replace(context.thread_id, self.team.messages)
        await self.emit(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=context.thread_id, content=answer
                )
            )
        )
        return {"answer": TicketAnswer(content=answer, requires_approval=False)}

    def _prompt(self, state: SupportState) -> str:
        context = state.context
        prompt = context.render(state.question, with_history=context.for_customer)

        if state.kb_snippets:
            prompt += "\n\nKnowledge base articles:\n" + "\n\n".join(state.kb_snippets)

        if state.result:
            prompt += f"\n\nA tool was run and returned:\n{state.result}"
            if state.corrected:
                # Without this the model reads a corrected amount as an error
                # and tells the rep to make up the difference, which is the
                # reviewer's decision being undone by the summary of it.
                prompt += (
                    "\nA reviewer changed the arguments before approving. That "
                    "is the decision, not a mistake: report what ran."
                )
        elif state.cancelled:
            prompt += "\n\nThe action was cancelled by a reviewer. Say so plainly."
        elif state.tool_error:
            prompt += f"\n\nA tool failed:\n{state.tool_error}"
        return prompt

    async def _history(self, state: SupportState) -> Any:
        """A single pass carries the thread in its prompt instead."""
        if state.context.for_customer:
            return None
        return await history().load(state.context.thread_id)

    def route_start(self, state: SupportState) -> str:
        """Only a customer's ticket is graded; the team's question is not one."""
        return "classify" if state.context.for_customer else "decide"

    def route_decision(self, state: SupportState) -> str:
        match state.decision:
            case SearchKnowledgeBase():
                return "knowledge"
            case RunTool():
                return "tool"
            case Escalate() if state.context.for_customer:
                return "escalate"
            case Escalate():
                # The team is the human it would be escalating to.
                return "respond"
            case _:
                return "respond"

    def route_answer(self, state: SupportState) -> str:
        """A customer's reply is sent by the delivery subgraph; the team's is
        already where it was going."""
        return "delivery" if state.context.for_customer else END

    def nodes(self) -> dict[str, Node]:
        """Only this graph's own steps. Subgraphs are added whole, in build()."""
        return {
            "classify": self.classify,
            "decide": self.decide,
            "escalate": self.escalate,
            "report_tool": self.report_tool,
            "respond": self.respond,
        }

    def build(self) -> StateGraph[SupportState, None, SupportState, SupportState]:
        graph: StateGraph[SupportState, None, SupportState, SupportState] = StateGraph(
            SupportState
        )
        self.add_nodes(graph)

        # Compiled subgraphs go in as nodes. They share the keys they need with
        # this state, so nothing has to be mapped across the boundary.
        graph.add_node("knowledge", build_knowledge_graph(self.config, self.emit))
        graph.add_node("tool", build_tool_graph(self.config, self.emit))
        graph.add_node("delivery", build_delivery_graph(self.config, self.emit))

        graph.add_conditional_edges(
            START, self.route_start, {"classify": "classify", "decide": "decide"}
        )
        graph.add_edge("classify", "decide")
        graph.add_conditional_edges(
            "decide",
            self.route_decision,
            {
                "knowledge": "knowledge",
                "tool": "tool",
                "escalate": "escalate",
                "respond": "respond",
            },
        )
        graph.add_edge("knowledge", "respond")
        graph.add_edge("tool", "report_tool")
        graph.add_edge("report_tool", "respond")
        graph.add_edge("escalate", END)
        graph.add_conditional_edges(
            "respond", self.route_answer, {"delivery": "delivery", END: END}
        )
        graph.add_edge("delivery", END)

        return graph


def build_support_graph(
    config: AgentConfig | None = None,
    saver: BaseCheckpointSaver[str] | None = None,
    emitter: Emitter = silent,
) -> CompiledStateGraph[SupportState, None, SupportState, SupportState]:
    """Compile a run's graph. Cheap, and the topology never varies; what varies
    is which model each purpose resolves to, and where its events go."""
    return SupportGraph(config, emitter).compile(saver or checkpointer())
