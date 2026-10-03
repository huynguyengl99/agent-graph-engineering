"""Draft text the agent could not finish, and the rule that it must be.

A model that does not know a value writes `{{refund amount}}` rather than
inventing one. Square brackets are already the citation form, so they are not
it. Nothing with a placeholder left in it may reach the customer, and the same
pattern is checked in the browser, here, and prompted for in the agent.
"""

import re

PLACEHOLDER = re.compile(r"\{\{\s*([^{}]{1,60}?)\s*\}\}")


def found(text: str) -> list[str]:
    """Each distinct placeholder, in the order it first appears."""
    seen: dict[str, None] = {}
    for match in PLACEHOLDER.finditer(text or ""):
        seen.setdefault(match.group(1), None)
    return list(seen)


def fill(text: str, values: dict[str, str]) -> str:
    def swap(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return PLACEHOLDER.sub(swap, text or "")


class UnfilledError(ValueError):
    """Raised rather than letting a half-written reply out."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(f"unfilled placeholders: {', '.join(names)}")


def refuse_if_unfilled(text: str) -> None:
    if names := found(text):
        raise UnfilledError(names)
