"""Contexts for tests, in the two shapes the topics build."""

from collections.abc import Sequence

from assistant.agents import Audience, Context, Ticket, Turn


def ticket_context(
    ticket_id: str = "t-1",
    title: str = "Charged twice",
    description: str = "My card shows two charges.",
    history: Sequence[str] = (),
) -> Context:
    return Context(
        thread_id=ticket_id,
        audience=Audience.CUSTOMER,
        ticket=Ticket(ticket_id=ticket_id, title=title, description=description),
        history=[Turn(role="thread", content=line) for line in history],
    )
