from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4

from assistant.guardrails import fence


class Audience(StrEnum):
    """Who the answer is for.

    The one field that decides whether a reply is screened, gated behind a
    person, and published - so it is stated rather than inferred from which
    graph happens to be running.
    """

    CUSTOMER = "customer"
    TEAM = "team"


@dataclass
class Ticket:
    """The ticket's own facts. Every field was typed by a customer."""

    ticket_id: str
    title: str
    description: str

    def render(self, history: list["Turn"] | None = None) -> str:
        body = [f"Title: {self.title}", f"Description: {self.description}"]
        if history:
            body.append("Conversation so far:")
            body.extend(f"- {turn.content}" for turn in history)
        return fence("TICKET", "\n".join(body))


@dataclass
class Turn:
    """One thing someone said, in the order it was said."""

    role: str
    content: str


@dataclass
class Context:
    """What a run is about, and who its answer is for.

    One shape for every graph: a ticket being worked, a question from the team,
    or both. A subgraph can then be composed by any parent, because the key they
    share has one type.
    """

    thread_id: str = ""
    audience: Audience = Audience.TEAM
    ticket: Ticket | None = None
    history: list[Turn] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        # A checkpoint round trip hands back the plain string it stored, and an
        # audience that is not the enum answers no to every question about it.
        self.audience = Audience(self.audience)

    @property
    def trace_key(self) -> str:
        """One question answered is one run; the thread is only where it sits."""
        return self.run_id

    @property
    def ticket_id(self) -> str:
        return self.ticket.ticket_id if self.ticket else ""

    @property
    def for_customer(self) -> bool:
        return self.audience == Audience.CUSTOMER

    def render(self, question: str = "", *, with_history: bool = False) -> str:
        """The ticket, and what is being asked of the model.

        `with_history` because a single-pass run has no message history of its
        own, so the thread has to be in the prompt; a conversation already sends
        it as messages, and repeating it there would send each turn twice.
        """
        parts: list[str] = []

        if self.ticket is not None:
            if question:
                parts.append("The agent is looking at this ticket:")
            parts.append(self.ticket.render(self.history if with_history else None))
        elif not self.for_customer:
            # Stated rather than left to inference: without it the model assumes
            # a customer is waiting and answers as though one had written in.
            parts.append(
                "No ticket is attached. There is no customer in this "
                "conversation; the support agent is asking you directly."
            )

        if question:
            parts.append(f"Their question: {question}")
        return "\n\n".join(parts)

    def untrusted_text(self) -> str:
        """Just the customer-written parts, for screening."""
        if self.ticket is None:
            return ""
        return "\n".join(
            [
                self.ticket.title,
                self.ticket.description,
                *(t.content for t in self.history),
            ]
        )
