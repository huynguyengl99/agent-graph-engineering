"""The parts every action on one viewset repeats."""

from collections.abc import Callable
from typing import Any

from drf_spectacular.utils import extend_schema


def tagged(tag: str, **shared: Any) -> Callable[..., Any]:
    """An `extend_schema` that already carries a viewset's tag and parameters,
    so each action declares only what it alone says."""

    def endpoint(summary: str, **kwargs: Any) -> Any:
        return extend_schema(summary=summary, tags=[tag], **shared, **kwargs)

    return endpoint
