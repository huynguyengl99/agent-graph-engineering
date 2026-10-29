from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from assistant.graphs.base import BaseGraph
from assistant.graphs.feed import AnswerFeed
from assistant.graphs.states import DeliveryState, Update
from assistant.graphs.states.base import Resuming
from assistant.guardrails import screen_reply
from assistant.messages.support import (
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ReplyBlockedMessage,
    ReplyBlockedPayload,
    ReplySentMessage,
    ReplySentPayload,
)
from assistant.prompts import ANSWER_PROMPT
from assistant.tools.core import Failed
from assistant.tools.reply import send_reply_to_customer
from assistant.tracing.nodes import Node


class DeliveryGraph(AnswerFeed, BaseGraph):
    """The only path to a customer, and the only irreversible step.

    A subgraph because it is the same pipeline wherever a draft comes from,
    and because keeping the gate in one place is the point: there is no second
    route to `send_reply`.

    The screen runs on every draft; the gate does not. Which drafts stop for a
    person is `needs_a_person`.
    """

    name = "delivery"

    async def delivery_screen(
        self, state: DeliveryState
    ) -> Command[Literal["delivery_approval", "delivery_send", "__end__"]]:
        """The machine check before the human one: a blocked draft never
        reaches the gate."""
        answer = state.answer
        ticket_id = state.context.ticket_id
        result = screen_reply(
            answer.content, ticket_id=ticket_id, instructions=ANSWER_PROMPT
        )
        findings = list(state.guardrail_findings) + result.rendered()
        if result.blocked:
            # Nothing follows: say so here, because no gate will.
            await self.emit(
                ReplyBlockedMessage(
                    payload=ReplyBlockedPayload(
                        ticket_id=ticket_id, draft=answer.content, findings=findings
                    )
                )
            )
            return Command(
                update={"guardrail_findings": findings, "reply_blocked": True},
                goto="__end__",
            )

        update = {"guardrail_findings": findings, "reply_blocked": False}
        waiting = self.needs_a_person(
            state.model_copy(update={"guardrail_findings": findings})
        )
        return Command(
            update=update, goto="delivery_approval" if waiting else "delivery_send"
        )

    async def delivery_approval(
        self, state: DeliveryState
    ) -> Command[Literal["delivery_await"]]:
        """Hand the draft to a person and stop.

        The findings go out with the proposal rather than being left in state
        for the parent to merge, because the reviewer needs them now and the
        run is about to end.
        """
        answer = state.answer
        await self.emit(
            ApprovalRequiredMessage(
                payload=ApprovalRequiredPayload(
                    ticket_id=state.context.thread_id,
                    draft=answer.content,
                    findings=list(state.guardrail_findings),
                )
            )
        )
        return Command(
            update={"awaiting": Resuming.REPLY_APPROVAL}, goto="delivery_await"
        )

    async def delivery_await(self, state: DeliveryState) -> DeliveryState:
        """Where the run stops while a reviewer reads the draft."""
        return state

    def entry(self, state: DeliveryState) -> str:
        """A fresh run screens the draft. A resumed one already has a verdict."""
        if state.resuming is not Resuming.REPLY_APPROVAL:
            return "delivery_screen"
        return "delivery_send" if state.approval_granted else "__end__"

    async def delivery_send(self, state: DeliveryState) -> Update:
        """The irreversible step."""
        answer = state.answer
        ticket_id = state.context.ticket_id
        outcome = await send_reply_to_customer(ticket_id, answer.content, approved=True)
        if isinstance(outcome, Failed):
            return {"tool_error": outcome.user_error}

        receipt = str(outcome.result)
        await self.emit(
            ReplySentMessage(
                payload=ReplySentPayload(
                    ticket_id=ticket_id, receipt=receipt, content=answer.content
                )
            )
        )
        return {"delivery_receipt": receipt}

    def needs_a_person(self, state: DeliveryState) -> bool:
        """Whether a person reads this before the customer does.

        Output findings all block outright, so a finding surviving to here is
        the input screen's: something in the ticket addressed the model. A
        handover has already sent for a person, so it does not wait for one.
        The answer does not get a say: asked, a model says yes every time.
        """
        if state.escalation_reason:
            return False
        return bool(state.guardrail_findings)

    # --- wiring -------------------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        return {
            "delivery_screen": self.delivery_screen,
            "delivery_approval": self.delivery_approval,
            "delivery_await": self.delivery_await,
            "delivery_send": self.delivery_send,
        }

    def build(self) -> StateGraph[DeliveryState, None, DeliveryState, DeliveryState]:
        graph: StateGraph[DeliveryState, None, DeliveryState, DeliveryState] = (
            StateGraph(DeliveryState)
        )
        self.add_nodes(graph)

        graph.add_conditional_edges(
            START,
            self.entry,
            {
                "delivery_screen": "delivery_screen",
                "delivery_send": "delivery_send",
                "__end__": END,
            },
        )
        graph.add_edge("delivery_send", END)
        graph.add_edge("delivery_await", END)

        return graph
