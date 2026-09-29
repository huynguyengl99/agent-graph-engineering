"""Instructions for the knowledge retrieval loop."""

REFINE_PROMPT = (
    "A knowledge base search returned nothing. Rewrite it as broader search "
    "terms: drop product-specific nouns, keep the underlying topic, and use "
    "the words documentation would use rather than the words the customer "
    "used. Return terms, never a question."
)
