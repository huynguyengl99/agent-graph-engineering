"""Money. The one place where getting an argument wrong costs something."""

from dataclasses import dataclass

from assistant.tools.core import InvalidInputError, NotFoundError, wrap_tool

MAX_SELF_SERVE = 500.0

# A stand-in for the billing system. Part 9 replaces it with a real client.
_SUBSCRIPTIONS: dict[str, dict[str, object]] = {
    "demo@example.com": {"plan": "Annual Pro", "monthly": 29.0, "renews": "2027-01-01"},
    "alice@example.com": {"plan": "Monthly Starter", "monthly": 9.0, "renews": "2026-11-01"},
}


@dataclass(frozen=True)
class Subscription:
    email: str
    plan: str
    monthly: float
    renews: str

    def render(self) -> str:
        return f"{self.plan}, £{self.monthly:.2f}/month, renews {self.renews}"


@wrap_tool(
    description="Look up a customer's current plan and renewal date.",
    tags=("billing", "read-only"),
    planner_hint="Use before quoting anything plan-specific.",
)
async def look_up_subscription(email: str) -> Subscription:
    """Find a customer's subscription.

    Args:
        email: The customer's email address.
    """
    record = _SUBSCRIPTIONS.get(email.strip().lower())
    if record is None:
        raise NotFoundError(
            f"No subscription for {email}.",
            user_message="I could not find a subscription for that address.",
        )
    return Subscription(
        email=email,
        plan=str(record["plan"]),
        monthly=float(record["monthly"]),  # type: ignore[arg-type]
        renews=str(record["renews"]),
    )


@wrap_tool(
    description="Refund an amount to a customer's card.",
    tags=("billing", "irreversible"),
    requires_approval=True,
    planner_hint="Money leaves the company. Always propose, never assume.",
)
async def issue_refund(email: str, amount: float, reason: str) -> str:
    """Refund a customer.

    Args:
        email: The customer being refunded.
        amount: Amount in GBP.
        reason: Why the refund is owed, for the audit trail.
    """
    if amount <= 0:
        raise InvalidInputError(
            f"issue_refund called with amount={amount}.",
            user_message="A refund has to be more than nothing.",
        )
    if amount > MAX_SELF_SERVE:
        # The approval gate is a human saying yes; this is the ceiling no
        # amount of saying yes gets past.
        raise InvalidInputError(
            f"issue_refund called with amount={amount}, over the "
            f"£{MAX_SELF_SERVE:.0f} self-serve ceiling.",
            user_message=(
                f"Refunds over £{MAX_SELF_SERVE:.0f} have to go through finance."
            ),
        )
    if not reason.strip():
        raise InvalidInputError(
            "issue_refund called with no reason.",
            user_message="A refund needs a reason for the audit trail.",
        )
    return f"Refunded £{amount:.2f} to {email} ({reason})."
