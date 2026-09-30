"""Cost is read off the spans, so it must survive an unpriceable model."""

from decimal import Decimal

from assistant.tracing.cost import (
    INPUT_TOKENS,
    OUTPUT_TOKENS,
    PROVIDER,
    REQUEST_MODEL,
    RunCost,
    cost_of_span,
)


def span(model: str, provider: str, inp: int, out: int) -> dict[str, object]:
    return {
        REQUEST_MODEL: model,
        PROVIDER: provider,
        INPUT_TOKENS: inp,
        OUTPUT_TOKENS: out,
    }


def test_a_span_that_is_not_a_model_call_has_no_cost() -> None:
    assert cost_of_span({"anything": "else"}) is None


def test_a_priced_model_produces_real_money() -> None:
    cost = cost_of_span(span("gpt-4o", "openai", 1000, 500))

    assert cost is not None
    assert cost.cost_usd > Decimal(0)
    assert cost.input_tokens == 1000
    assert cost.output_tokens == 500
    assert cost.priced is True


def test_an_unpriced_model_still_reports_tokens() -> None:
    """The scripted model has no price table. Reporting 0.00 as if it were
    free would be a lie; `priced` is what makes it readable."""
    cost = cost_of_span(span("scripted", "scripted", 10, 20))

    assert cost is not None
    assert cost.cost_usd == Decimal(0)
    assert cost.total_tokens == 30
    assert cost.priced is False


def test_one_unpriced_call_taints_the_run_total() -> None:
    priced = cost_of_span(span("gpt-4o", "openai", 100, 50))
    unpriced = cost_of_span(span("scripted", "scripted", 10, 5))
    assert priced is not None and unpriced is not None

    total = priced + unpriced
    assert total.calls == 2
    assert total.total_tokens == 165
    # A partially-priced total is not a number you can quote.
    assert total.priced is False


def test_an_empty_run_costs_nothing() -> None:
    assert RunCost().as_dict()["total_tokens"] == 0


class TestLocalPrices:
    """The pinned genai-prices predates the Claude 5 family."""

    def test_a_model_the_price_table_misses_falls_back_locally(self) -> None:
        cost = cost_of_span(span("claude-sonnet-5", "anthropic", 1_000_000, 0))

        assert cost is not None
        assert cost.priced is True
        assert cost.cost_usd == Decimal("2.00"), "Sonnet 5 input is $2/MTok"

    def test_output_is_priced_separately(self) -> None:
        cost = cost_of_span(span("claude-sonnet-5", "anthropic", 0, 1_000_000))

        assert cost is not None
        assert cost.cost_usd == Decimal("10.00")

    def test_a_model_in_neither_table_is_still_honestly_unpriced(self) -> None:
        cost = cost_of_span(span("some-future-model", "anthropic", 100, 50))

        assert cost is not None
        assert cost.priced is False
        assert "anthropic:some-future-model" in cost.unpriced_models

    def test_genai_prices_still_wins_where_it_knows_the_model(self) -> None:
        """The local table is a fallback, not an override to drift against."""
        cost = cost_of_span(span("claude-haiku-4-5", "anthropic", 1_000_000, 0))

        assert cost is not None
        assert cost.priced is True
        assert cost.cost_usd == Decimal("1.00")
