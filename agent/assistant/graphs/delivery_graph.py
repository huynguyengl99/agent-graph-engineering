from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from assistant.graphs.base import BaseGraph
from assistant.graphs.feed import AnswerFeed
from assistant.graphs.states import DeliveryState, Update
from assistant.graphs.states.base import ReplyRun
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
    ) -> Command[Literal["delivery_approval", "delivery_send", "delivery_done"]]:
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
                update={
                    "guardrail_findings": findings,
                    "reply_run": ReplyRun.BLOCKED,
                },
                goto="delivery_done",
            )

        update: dict[str, Any] = {"guardrail_findings": findings}
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
        return Command(update={"reply_run": ReplyRun.PENDING}, goto="delivery_await")

    async def delivery_await(self, state: DeliveryState) -> DeliveryState:
        """Where the run stops while a reviewer reads the draft."""
        return state

    async def delivery_start(
        self, state: DeliveryState
    ) -> Command[Literal["delivery_screen", "delivery_send", "delivery_done"]]:
        """Where a run enters, and the whole of the resume.

        Screening again a draft a reviewer has answered would ask the guard a
        question it has already answered.
        """
        match state.reply_run:
            case ReplyRun.APPROVED:
                return Command(goto="delivery_send")
            case ReplyRun.REJECTED:
                return Command(goto="delivery_done")
            case _:
                return Command(goto="delivery_screen")

    async def delivery_done(self, state: DeliveryState) -> DeliveryState:
        """One exit, whatever happened inside."""
        return state

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
        return {"delivery_receipt": receipt, "reply_run": ReplyRun.SENT}

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
            "delivery_start": self.delivery_start,
            "delivery_screen": self.delivery_screen,
            "delivery_approval": self.delivery_approval,
            "delivery_await": self.delivery_await,
            "delivery_send": self.delivery_send,
            "delivery_done": self.delivery_done,
        }

    def build(self) -> StateGraph[DeliveryState, None, DeliveryState, DeliveryState]:
        graph: StateGraph[DeliveryState, None, DeliveryState, DeliveryState] = (
            StateGraph(DeliveryState)
        )
        self.add_nodes(graph)

        graph.add_edge(START, "delivery_start")
        graph.add_edge("delivery_send", "delivery_done")
        graph.add_edge("delivery_await", "delivery_done")
        graph.add_edge("delivery_done", END)

        return graph
