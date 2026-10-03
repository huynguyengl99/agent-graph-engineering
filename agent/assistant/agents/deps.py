from dataclasses import dataclass, field
from uuid import uuid4

from assistant.guardrails import fence


@dataclass
class TicketContext:
    """Everything an agent may read about the ticket it is working on."""

    ticket_id: str
    title: str
    description: str
    history: list[str] = field(default_factory=list)

    @property
    def trace_key(self) -> str:
        return self.ticket_id

    def render(self) -> str:
        # Every field here was typed by a customer, so all of it is fenced.
        body = [f"Title: {self.title}", f"Description: {self.description}"]
        if self.history:
            body.append("Conversation so far:")
            body.extend(f"- {line}" for line in self.history)
        return fence("TICKET", "\n".join(body))

    def untrusted_text(self) -> str:
        """Just the customer-written parts, for screening."""
        return "\n".join([self.title, self.description, *self.history])


@dataclass
class ChatContext:
    """What the assistant knows about the rep's conversation.

    The ticket is optional: a conversation may be opened about one, or be a
    general question with no ticket at all.
    """

    conversation_id: str
    history: list[tuple[str, str]] = field(default_factory=list)
    ticket: TicketContext | None = None
    # One question answered is one run; the conversation is only where it sits.
    run_id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def trace_key(self) -> str:
        return self.run_id

    def render(self, question: str) -> str:
        """The ticket and the question, and deliberately not the history.

        Earlier turns reach the model as its own message history, so repeating
        them here as "user: ... assistant: ..." would send each one twice and
        flatten a tool call into a line of prose. `history` survives to seed that
        store for a conversation the agent has not answered before.
        """
        parts: list[str] = []
        if self.ticket is not None:
            parts.append("The agent is looking at this ticket:")
            parts.append(self.ticket.render())
        else:
            # Stated rather than left to inference: without it the model assumes
            # a customer is waiting and answers as though one had written in.
            parts.append(
                "No ticket is attached. There is no customer in this "
                "conversation; the support agent is asking you directly."
            )
        parts.append(f"Their question: {question}")
        return "\n\n".join(parts)
