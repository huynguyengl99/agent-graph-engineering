"""A tool's arguments, as JSON Schema.

The same schema does three jobs: the planner fills it, the reviewer's form is
generated from it, and nobody hand-writes a form per tool. Derived from the
signature so it cannot drift from the function it describes.
"""

import inspect
import re
from collections.abc import Callable
from typing import Any

from pydantic import create_model

# The approval flag is `wrap_tool` machinery, not an argument a caller chooses.
INTERNAL = frozenset({"approved"})

_ARG_LINE = re.compile(r"^\s{4,}(\w+):\s*(.+)$")


def argument_docs(func: Callable[..., Any]) -> dict[str, str]:
    """Descriptions from the `Args:` block of a Google-style docstring.

    Worth parsing: it is the only place an argument's meaning is already
    written down, and the reviewer's form needs it as field help.
    """
    doc = inspect.getdoc(func) or ""
    if "Args:" not in doc:
        return {}

    descriptions: dict[str, str] = {}
    for line in doc.split("Args:", 1)[1].splitlines():
        if line.strip() and not line.startswith(" "):
            break  # a new section, e.g. Returns:
        if match := _ARG_LINE.match(line):
            descriptions[match.group(1)] = match.group(2).strip()
    return descriptions


def arguments_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """JSON Schema for everything a caller passes."""
    unwrapped = inspect.unwrap(func)
    docs = argument_docs(unwrapped)

    fields: dict[str, Any] = {}
    for name, parameter in inspect.signature(unwrapped).parameters.items():
        if name in INTERNAL or parameter.kind in (
            parameter.VAR_POSITIONAL,
            parameter.VAR_KEYWORD,
        ):
            continue
        annotation = (
            Any
            if parameter.annotation is inspect.Parameter.empty
            else parameter.annotation
        )
        default = (
            ... if parameter.default is inspect.Parameter.empty else parameter.default
        )
        fields[name] = (annotation, default)

    schema: dict[str, Any] = create_model("Arguments", **fields).model_json_schema()
    for name, description in docs.items():
        if name in schema.get("properties", {}):
            schema["properties"][name]["description"] = description
    schema.pop("title", None)
    return schema


def split_arguments(
    schema: dict[str, Any], proposed: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Keep what the tool accepts; report the rest.

    A model that proposes `customer_email` for an `email` argument is not
    hallucinating a tool, just a name, and a person can fix that at the gate.
    Passing it through would crash the call with a TypeError instead, and
    keeping it silently would show the reviewer a form that does not match what
    would run - the argument is not on the form, so they cannot see it, correct
    it, or know why the field they can see is empty.
    """
    accepted = set(schema.get("properties", {}))
    kept = {name: value for name, value in proposed.items() if name in accepted}
    return kept, sorted(set(proposed) - accepted)


def missing_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """Required arguments with nothing usable in them."""
    required = schema.get("required", [])
    names = required if isinstance(required, list) else []
    return [
        str(name)
        for name in names
        if arguments.get(name) is None or arguments.get(name) == ""
    ]
