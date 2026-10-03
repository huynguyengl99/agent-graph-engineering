"""One connection to the agent, whoever is asking and wherever the answer lands.

Three relays used to open it: a ticket's customer run, a ticket's team run, and
a conversation. They differed in what they wrote down, not in how they talked,
so the talking lives here and what-to-write-down is a `Sink`.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from django.conf import settings

import structlog

from helpdesk.agent_client.agent.client import AgentClient
from helpdesk.agent_client.agent_hub_support_topic.client import (
    AgentHubSupportTopicClient,
)
from helpdesk.agent_client.agent_hub_support_topic.messages import (
    AnswerMessage,
    ApprovalDecisionMessage,
    ApprovalDecisionPayload,
    ApprovalRequiredMessage,
    ChatCompleteMessage,
    ChatErrorMessage,
    ChatTokenMessage,
    ClassifiedMessage,
    DecidedMessage,
    IncomingMessage,
    ReasonedMessage,
    ReasoningDeltaMessage,
    ReplayRequestMessage,
    ReplayRequestPayload,
    ReplyBlockedMessage,
    ReplySentMessage,
    RunRequestMessage,
    RunRequestPayload,
    ToolApprovalMessage,
    ToolDecisionMessage,
    ToolDecisionPayload,
    ToolRanMessage,
    TriageErrorMessage,
)
from helpdesk.core.agent_connection import agent_headers
from helpdesk.core.services.cursors import advance, last_handled

logger = structlog.get_logger(__name__)

_background: set[asyncio.Task[None]] = set()


def spawn(coro: "Coroutine[Any, Any, None]") -> None:
    """Run detached, keeping a strong reference.

    asyncio holds only a weak reference to a running task, so a detached one can
    be collected mid-flight. The discard callback stops the set growing.
    """
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


class Sink:
    """Where a run's events are written down. Every hook is optional."""

    async def classified(self, category: str, priority: str, why: str) -> None: ...
    async def decided(self, decision: str, why: str) -> None: ...
    async def drafted(self, content: str, requires_approval: bool) -> None: ...
    async def approval_required(self, draft: str, findings: list[str]) -> None: ...
    async def reply_sent(self) -> None: ...
    async def reply_blocked(self, findings: list[str]) -> None: ...
    async def token(self, delta: str) -> None: ...
    async def answered(self, content: str) -> None: ...
    async def tool_proposed(self, payload: Any) -> None: ...
    async def tool_ran(self, payload: Any) -> None: ...
    async def reasoning_delta(self, delta: str) -> None: ...
    async def reasoned(self, content: str, decision: str, model: str) -> None: ...
    async def failed(self, message: str) -> None: ...


class _Handle(AgentHubSupportTopicClient):
    """Forwards the topic's events to the relay that opened it."""

    async def dispatch_frame(self, py_object: dict[str, Any]) -> None:
        """The sequence and the agent's topic ride the envelope, not the message."""
        relay: Any = self.connection
        relay.incoming_seq = int(py_object.get("seq") or 0)
        relay.agent_topic = self.topic
        await super().dispatch_frame(py_object)

    async def handle_message(self, message: IncomingMessage) -> None:
        relay: Any = self.connection
        await relay.on_event(message)


Outgoing = RunRequestPayload | ApprovalDecisionPayload | ToolDecisionPayload


class SupportRun(AgentClient):
    """One request, then disconnect.

    A run may end parked at a gate instead of at an answer, in which case the
    connection closes with the run still checkpointed in the agent. The
    reviewer's decision opens a fresh one and subscribes again.
    """

    def __init__(self, audience: str, thread_id: str, request: Outgoing, sink: Sink):
        super().__init__(settings.AGENT_WS_URL, headers=agent_headers())
        self.audience = audience
        self.thread_id = thread_id
        self.payload = request
        self.sink = sink
        # Both set by the handle before it forwards an event.
        self.incoming_seq = 0
        self.agent_topic = ""

    async def send_init_message(self) -> None:
        topic = self.topic(_Handle, audience=self.audience, thread_id=self.thread_id)
        # Subscribed before the request, or the run's own events race the
        # subscription and the first ones are dropped.
        await topic.subscribe()

        # Whatever finished while nobody was subscribed, before the new request.
        await topic.send_message(
            ReplayRequestMessage(
                payload=ReplayRequestPayload(since=await last_handled(topic.topic))
            )
        )

        match self.payload:
            case RunRequestPayload():
                await topic.send_message(RunRequestMessage(payload=self.payload))
            case ApprovalDecisionPayload():
                await topic.send_message(ApprovalDecisionMessage(payload=self.payload))
            case _:
                await topic.send_message(ToolDecisionMessage(payload=self.payload))

    async def disconnect(self, code: int = 1000, reason: str = "") -> None:
        """Closing a run that never opened a socket is not an error.

        The terminal handlers below call this unconditionally, and the agent may
        also have dropped the connection first.
        """
        if getattr(self, "websocket", None) is None:
            return
        await super().disconnect(code, reason)

    async def on_event(self, message: IncomingMessage) -> None:  # noqa: PLR0912
        match message:
            case ClassifiedMessage(payload=p):
                await self.sink.classified(p.category, p.priority, p.reasoning)
            case DecidedMessage(payload=p):
                await self.sink.decided(p.decision, p.reasoning)
            case AnswerMessage(payload=p):
                await self.sink.drafted(p.content, p.requires_approval)
            case ApprovalRequiredMessage(payload=p):
                await self.sink.approval_required(p.draft, list(p.findings or []))
                await self.disconnect()
            case ReplySentMessage():
                await self.sink.reply_sent()
                await self.disconnect()
            case ReplyBlockedMessage(payload=p):
                await self.sink.reply_blocked(list(p.findings or []))
                await self.disconnect()
            case ChatTokenMessage(payload=p):
                await self.sink.token(p.delta)
            case ReasoningDeltaMessage(payload=p):
                await self.sink.reasoning_delta(p.delta)
            case ReasonedMessage(payload=p):
                await self.sink.reasoned(p.content, p.decision, p.model)
            case ToolApprovalMessage(payload=p):
                await self.sink.tool_proposed(p)
                await self.disconnect()
            case ToolRanMessage(payload=p):
                await self.sink.tool_ran(p)
            case ChatCompleteMessage(payload=p):
                await self.sink.answered(p.content)
                await self.disconnect()
            case TriageErrorMessage(payload=p) | ChatErrorMessage(payload=p):
                await self.sink.failed(p.message)
                await self.disconnect()
            case _:
                # A heartbeat, or a message type the agent gained and this relay
                # has not been taught yet. Ignored on purpose, and said so,
                # because an unhandled branch that falls off the end reads like
                # an oversight.
                pass

        await advance(self.agent_topic, self.incoming_seq)
