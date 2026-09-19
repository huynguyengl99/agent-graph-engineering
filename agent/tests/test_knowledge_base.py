"""Ranking is tested against the pure function; the wrapper is tested via the tool."""

from triage.tools.knowledge_base import _search, search_knowledge_base


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


async def test_tool_returns_articles_in_a_tool_output() -> None:
    output = await search_knowledge_base("invoice billing refund")
    assert output.ok
    assert output.result


async def test_tool_rejects_an_empty_query() -> None:
    output = await search_knowledge_base("   ")
    assert output.error_type == "invalid_input"
    assert output.result is None
