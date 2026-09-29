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
