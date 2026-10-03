"""Nothing half-written reaches the customer."""

import pytest

from helpdesk.tickets.services.placeholders import (
    UnfilledError,
    fill,
    found,
    refuse_if_unfilled,
)


class TestFinding:
    def test_a_draft_names_what_it_could_not_fill(self) -> None:
        assert found("Refunded {{amount}} to {{card}}.") == ["amount", "card"]

    def test_the_same_one_twice_is_one_field(self) -> None:
        assert found("{{name}}, thanks {{ name }}.") == ["name"]

    def test_a_citation_is_not_a_placeholder(self) -> None:
        """Square brackets are how the agent cites an article."""
        assert found("Per [kb-003], annual plans refund within 14 days.") == []

    def test_finished_text_has_none(self) -> None:
        assert found("Refunded $29.00.") == []


class TestFilling:
    def test_every_mention_is_replaced(self) -> None:
        assert fill("{{a}} and {{ a }}", {"a": "9"}) == "9 and 9"

    def test_one_left_out_stays_a_placeholder(self) -> None:
        assert fill("{{a}} {{b}}", {"a": "9"}) == "9 {{b}}"


class TestRefusing:
    def test_it_names_what_is_missing(self) -> None:
        with pytest.raises(UnfilledError) as raised:
            refuse_if_unfilled("Refunded {{amount}}.")

        assert raised.value.names == ["amount"]

    def test_finished_text_passes(self) -> None:
        refuse_if_unfilled("Refunded $29.00.")
