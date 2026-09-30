"""Prices for models the pinned genai-prices does not know yet.

genai-prices is pinned at 0.0.55 because newer releases zero pydantic-ai's
token counts (see pyproject), and that release predates the Claude 5 family.
Without this table a Claude run reports its tokens and no cost at all, which
makes the whole point of measuring cost moot.

Hand-maintained, so it goes stale: check it against
https://www.anthropic.com/pricing when a model is added or a price moves.
Anything absent here still reports `priced: false` rather than guessing.

Last checked: 2026-09-30. USD per million tokens, (input, output).
"""

from decimal import Decimal

MILLION = Decimal(1_000_000)

PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "anthropic:claude-sonnet-5": (Decimal("2.00"), Decimal("10.00")),
    "anthropic:claude-opus-5": (Decimal("5.00"), Decimal("25.00")),
    "anthropic:claude-opus-5-5": (Decimal("4.00"), Decimal("20.00")),
    "anthropic:claude-fable-5-1": (Decimal("10.00"), Decimal("50.00")),
}


def local_price(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> Decimal | None:
    """Cost from the table above, or None when the model is not in it."""
    entry = PRICES.get(f"{provider}:{model}")
    if entry is None:
        return None
    per_input, per_output = entry
    return (per_input * input_tokens + per_output * output_tokens) / MILLION
