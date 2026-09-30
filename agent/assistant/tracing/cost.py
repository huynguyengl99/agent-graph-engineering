"""What a run cost, derived from the spans already collected.

Pydantic AI stamps every model call with its provider, model, and token counts,
so cost needs no plumbing through the agents: it is a read over the trace store.

A model with no entry in the price table (the scripted one, or a provider
genai-prices has not seen) still reports its tokens. `priced` says whether the
money figure can be trusted, so an unpriced run reads as "0.00, unpriced"
rather than silently as "free".
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from genai_prices import calc_price

from assistant.tracing.prices import local_price

INPUT_TOKENS = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
REQUEST_MODEL = "gen_ai.request.model"
PROVIDER = "gen_ai.system"


@dataclass(frozen=True, slots=True)
class _Usage:
    """Structurally satisfies genai-prices' AbstractUsage protocol.

    Spans only carry the two token counts; the rest are zero rather than absent
    so a cached-token price component cannot silently go missing.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    input_audio_tokens: int = 0
    cache_audio_read_tokens: int = 0
    output_audio_tokens: int = 0


@dataclass(frozen=True, slots=True)
class RunCost:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    calls: int = 0
    priced: bool = True
    # Which models had no price table, so a report can name them instead of
    # guessing why the total is unpriced.
    unpriced_models: frozenset[str] = frozenset()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "RunCost") -> "RunCost":
        return RunCost(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            calls=self.calls + other.calls,
            priced=self.priced and other.priced,
            unpriced_models=self.unpriced_models | other.unpriced_models,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": float(self.cost_usd),
            "priced": self.priced,
            "unpriced_models": sorted(self.unpriced_models),
        }


def cost_of_span(attributes: dict[str, Any]) -> RunCost | None:
    """Cost for one model call, or None if this span is not one."""
    model = attributes.get(REQUEST_MODEL)
    if not model:
        return None

    input_tokens = int(attributes.get(INPUT_TOKENS) or 0)
    output_tokens = int(attributes.get(OUTPUT_TOKENS) or 0)
    provider = str(attributes.get(PROVIDER) or "")

    try:
        price = calc_price(
            _Usage(input_tokens, output_tokens), str(model), provider_id=provider
        )
    except (LookupError, ValueError):
        # genai-prices is pinned to a release that predates some models we
        # run; fall back to the hand-maintained table before giving up.
        local = local_price(provider, str(model), input_tokens, output_tokens)
        if local is not None:
            return RunCost(input_tokens, output_tokens, local, calls=1)
        return RunCost(
            input_tokens,
            output_tokens,
            Decimal(0),
            calls=1,
            priced=False,
            unpriced_models=frozenset({f"{provider}:{model}"}),
        )

    return RunCost(input_tokens, output_tokens, price.total_price, calls=1)
