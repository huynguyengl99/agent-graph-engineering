from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

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
from assistant.graphs.delivery_graph import DeliveryGraph
from assistant.graphs.feed import AnswerFeed
from assistant.graphs.knowledge_graph import KnowledgeGraph
from assistant.graphs.states import SupportState, Update
from assistant.graphs.tool_graph import ToolGraph
from assistant.guardrails import screen_input
from assistant.messages.support import (
    ChatCompleteMessage,
    ChatCompletePayload,
    ChatTokenMessage,
    ChatTokenPayload,
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


def _route_for(
    decision: Decision, for_customer: bool
) -> Literal["knowledge", "tool", "support_escalate", "support_respond"]:
    """Where a decision sends the run.

    A pure function rather than an edge map: the node still declares its
    destinations in its own return type, and this is the one line of it worth
    reading on its own.
    """
    match decision:
        case SearchKnowledgeBase():
            return "knowledge"
        case RunTool():
            return "tool"
        case Escalate() if for_customer:
            return "support_escalate"
        case _:
            # The team is the human it would be escalating to.
            return "support_respond"


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

    async def support_start(
        self, state: SupportState
    ) -> Command[Literal["support_classify", "support_decide"]]:
        """Only a customer's ticket is graded; the team's question is not one."""
        return Command(
            goto="support_classify" if state.context.for_customer else "support_decide"
        )

    async def support_classify(
        self, state: SupportState
    ) -> Command[Literal["support_decide"]]:
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
        return Command(
            update={
                "classification": classification,
                "guardrail_findings": attempts.rendered(),
            },
            goto="support_decide",
        )

    async def support_decide(
        self, state: SupportState
    ) -> Command[Literal["knowledge", "tool", "support_escalate", "support_respond"]]:
        """What happens next, and where the run goes to do it."""
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
        return Command(update=update, goto=_route_for(decision, context.for_customer))

    async def support_escalate(
        self, state: SupportState
    ) -> Command[Literal["delivery"]]:
        """Hand the ticket over, and tell the customer so.

        The notice leaves by the one route out, like any other reply.
        """
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
        return Command(
            update={"escalation_reason": reason, "answer": answer}, goto="delivery"
        )

    async def support_report_tool(
        self, state: SupportState
    ) -> Command[Literal["support_respond"]]:
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
        return Command(goto="support_respond")

    async def support_respond(
        self, state: SupportState
    ) -> Command[Literal["delivery", "__end__"]]:
        """The one node both audiences end at, writing for whoever is reading.

        A customer's reply is sent by the delivery subgraph; the team's is
        already where it was going.
        """
        if state.context.for_customer:
            return Command(update=await self._reply_to_customer(state), goto="delivery")
        return Command(update=await self._answer_the_team(state), goto="__end__")

    async def _reply_to_customer(self, state: SupportState) -> Update:
        """Written here, screened and sent by the delivery subgraph.

        Whether a person sees it first is decided there, after the screening
        that informs it - so the answer does not claim to know.
        """
        context = state.context
        answer = await self.answerer.run(self._prompt(state), context)
        await self.answered(context.ticket_id, answer)
        return {"answer": answer}

    async def _answer_the_team(self, state: SupportState) -> Update:
        context = state.context
        parts: list[str] = []
        async for delta in self.team.stream(
            self._prompt(state), context, await self._history(state)
        ):
            parts.append(delta)
            # Published, not written to the graph's stream: every subscriber
            # watching this ticket sees it arrive, not only the socket that
            # asked. The finished text follows as the record.
            await self.emit(
                ChatTokenMessage(
                    payload=ChatTokenPayload(
                        conversation_id=context.thread_id, delta=delta
                    )
                ),
                replayable=False,
            )

        answer = "".join(parts)
        # Everything this turn saw, the model's own reply included, so the next
        # turn reads its actions as the calls they were rather than as prose.
        await history().replace(context.thread_id, self.team.messages)
        await self.emit(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=context.thread_id,
                    content=answer,
                    model=self.answer_model,
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

    def route_after_tool(self, state: SupportState) -> str:
        """A planner asked for a tool and finding none is not a tool call.

        The decider can route here and the planner still answer `NoToolNeeded`,
        which used to file a tool call with no tool in it: on a customer's run
        that reached them as a box saying `RAN` about nothing at all.

        A routing method rather than a `Command`, because the node it follows
        is a compiled subgraph: only the parent can say what comes after one.
        """
        return "support_report_tool" if state.tool else "support_respond"

    # --- wiring -------------------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        """Only this graph's own steps. Subgraphs are added whole, in build()."""
        return {
            "support_start": self.support_start,
            "support_classify": self.support_classify,
            "support_decide": self.support_decide,
            "support_escalate": self.support_escalate,
            "support_report_tool": self.support_report_tool,
            "support_respond": self.support_respond,
        }

    def build(self) -> StateGraph[SupportState, None, SupportState, SupportState]:
        graph: StateGraph[SupportState, None, SupportState, SupportState] = StateGraph(
            SupportState
        )
        self.add_nodes(graph)

        # Compiled subgraphs go in as nodes. They share the keys they need with
        # this state, so nothing has to be mapped across the boundary - and
        # where a run goes after one is the parent's to say, because a subgraph
        # cannot route into the graph that owns it.
        graph.add_node("knowledge", KnowledgeGraph(self.config, self.emit).subgraph())
        graph.add_node("tool", ToolGraph(self.config, self.emit).subgraph())
        graph.add_node("delivery", DeliveryGraph(self.config, self.emit).subgraph())

        graph.add_edge(START, "support_start")
        graph.add_edge("knowledge", "support_respond")
        graph.add_conditional_edges(
            "tool",
            self.route_after_tool,
            {
                "support_report_tool": "support_report_tool",
                "support_respond": "support_respond",
            },
        )
        graph.add_edge("delivery", END)

        return graph
