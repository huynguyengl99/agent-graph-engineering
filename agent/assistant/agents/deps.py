from dataclasses import dataclass, field

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

    @property
    def trace_key(self) -> str:
        return self.conversation_id

    def render(self, question: str) -> str:
        parts: list[str] = []
        if self.ticket is not None:
            parts.append("The agent is looking at this ticket:")
            parts.append(self.ticket.render())
        if self.history:
            parts.append("Earlier in this conversation:")
            parts.extend(f"{role}: {content}" for role, content in self.history)
        parts.append(f"Their question: {question}")
        return "\n\n".join(parts)
