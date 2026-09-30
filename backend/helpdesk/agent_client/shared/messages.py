from typing import Literal

from pydantic import BaseModel


class ModelOverrides(BaseModel):
    """Which model fills each purpose for this run.

    The caller may set any subset; unset purposes fall through to the
    deployment default. It cannot change *which* purpose a step runs under,
    which is what keeps routing off the wrong class of model."""

    decision: str | None = None
    answer: str | None = None


class PingMessage(BaseModel):
    """Simple ping message to check WebSocket connection status."""

    action: Literal["ping"] = "ping"
    payload: None = None


class PongMessage(BaseModel):
    """Simple pong message response to ping requests."""

    action: Literal["pong"] = "pong"
    payload: None = None
