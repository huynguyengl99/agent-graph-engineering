"""Customer-facing actions. These are the ones that need a human first."""

from triage.tools.core import InvalidInputError, wrap_tool


@wrap_tool(
    description="Send a written reply to the customer on this ticket.",
    tags=("customer", "irreversible"),
    requires_approval=True,
    planner_hint="The customer sees this. It cannot be unsent.",
)
async def send_reply_to_customer(ticket_id: str, body: str) -> str:
    """Post a reply visible to the customer.

    Args:
        ticket_id: The ticket being replied to.
        body: The message the customer will read.
    """
    if not body.strip():
        raise InvalidInputError(
            "send_reply_to_customer called with an empty body.",
            user_message="There is nothing to send.",
        )
    # A real deployment posts to the helpdesk here. The approval gate in
    # `wrap_tool` is what matters at this stage of the series.
    return f"Reply queued for ticket {ticket_id} ({len(body)} chars)."
