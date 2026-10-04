from dataclasses import dataclass

from assistant.tools.core import InvalidInputError, wrap_tool

# A stand-in for a real retrieval backend. Part 9 replaces it with pgvector.
_ARTICLES: list[tuple[str, str, str]] = [
    (
        "kb-001",
        "Resetting your password",
        "Use the 'Forgot password' link on the sign-in page. The reset email "
        "expires after 30 minutes. If it never arrives, check spam, then confirm "
        "the address on file in Account Settings.",
    ),
    (
        "kb-002",
        "Understanding your invoice",
        "Invoices are issued on the first of each month and cover the previous "
        "billing period. Proration appears as a separate line item when a plan "
        "changes mid-cycle.",
    ),
    (
        "kb-003",
        "Refund policy",
        "Annual plans are refundable within 14 days of purchase. Monthly plans "
        "are not refundable, but cancelling stops the next charge immediately.",
    ),
    (
        "kb-004",
        "API rate limits",
        "The default limit is 1000 requests per minute per API key. Exceeding it "
        "returns HTTP 429 with a Retry-After header. Limits are raised on request "
        "for Enterprise plans.",
    ),
    (
        "kb-005",
        "Two-factor authentication",
        "Enable 2FA under Account Settings > Security. Recovery codes are shown "
        "once at setup. Losing both the device and the codes requires identity "
        "verification with support.",
    ),
]


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    body: str

    def render(self) -> str:
        return f"[{self.id}] {self.title}\n{self.body}"


MIN_TERM_LENGTH = 3

# Without these, "charged twice for the same plan" scores every article that
# contains "the", and the top hit for a billing question was the rate-limit
# page. A real retrieval backend does this with IDF; five articles do not
# justify one.
STOPWORDS = frozenset(
    """a an and are as at be but by can for from has have how i in is it my
    not of on or our that the their them they this to was what when where
    which who why will with you your""".split()
)

# A term in the title says more about what an article is about than the same
# term buried in its body.
TITLE_WEIGHT = 3


@wrap_tool(
    description="Look up a documented answer in the support knowledge base.",
    tags=("knowledge", "read-only"),
    # The knowledge branch calls this directly, with a refine loop around it.
    # A planner offered it as well would reach the articles by a route that has
    # no second attempt.
    selectable=False,
)
async def search_knowledge_base(query: str, limit: int = 3) -> list[Article]:
    """Search the knowledge base.

    Args:
        query: Search terms. Plain words, not a question.
        limit: Maximum number of articles to return.
    """
    if not query.strip():
        raise InvalidInputError(
            "search_knowledge_base called with an empty query.",
            user_message="I could not work out what to search for.",
        )
    return _search(query, limit)


def _search(query: str, limit: int = 3) -> list[Article]:
    """Naive keyword overlap search over the built-in article set."""
    terms = {
        term
        for term in query.lower().split()
        if len(term) >= MIN_TERM_LENGTH and term not in STOPWORDS
    }
    if not terms:
        return []

    scored: list[tuple[int, Article]] = []
    for article_id, title, body in _ARTICLES:
        lowered_title, lowered_body = title.lower(), body.lower()
        score = sum(
            TITLE_WEIGHT if term in lowered_title else 1
            for term in terms
            if term in lowered_title or term in lowered_body
        )
        if score:
            scored.append((score, Article(article_id, title, body)))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [article for _, article in scored[:limit]]
