"""Ranking is tested against the pure function; the wrapper is tested via the tool."""

from assistant.tools.core import Failed, Succeeded
from assistant.tools.knowledge_base import _search, search_knowledge_base


def test_ranks_by_term_overlap() -> None:
    results = _search("password reset email")
    assert results
    assert results[0].id == "kb-001"


def test_returns_nothing_for_unmatched_query() -> None:
    assert _search("quantum tunnelling") == []


def test_ignores_short_noise_words() -> None:
    assert _search("is a of") == []


def test_respects_the_limit() -> None:
    assert len(_search("account plan billing api", limit=2)) <= 2


async def test_tool_returns_articles_in_an_outcome() -> None:
    outcome = await search_knowledge_base("invoice billing refund")
    assert isinstance(outcome, Succeeded)
    assert outcome.result


async def test_tool_rejects_an_empty_query() -> None:
    outcome = await search_knowledge_base("   ")
    assert isinstance(outcome, Failed)
    assert outcome.kind == "invalid_input"


class TestRanking:
    """A real run found the rate-limit page top of a billing search."""

    def test_stopwords_do_not_decide_the_ranking(self) -> None:
        hits = [article.id for article in _search("charged twice for the same plan")]

        assert hits[0] == "kb-002", "the invoice article answers this question"

    def test_a_title_match_outranks_a_body_mention(self) -> None:
        # "plan" appears in the rate-limit body; "invoice" is a title word.
        assert [a.id for a in _search("invoice")][0] == "kb-002"

    def test_a_query_of_only_stopwords_finds_nothing(self) -> None:
        assert _search("what is the for and of") == []

    def test_each_topic_finds_its_own_article(self) -> None:
        for query, expected in [
            ("password reset", "kb-001"),
            ("refund policy annual", "kb-003"),
            ("api rate limits", "kb-004"),
            ("two-factor authentication", "kb-005"),
        ]:
            assert [a.id for a in _search(query)][0] == expected, query
