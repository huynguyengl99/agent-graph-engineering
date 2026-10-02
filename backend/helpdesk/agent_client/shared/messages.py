from typing import Literal

from pydantic import BaseModel


class ModelOverrides(BaseModel):
    """Which model fills each purpose for this run.

    The caller may set any subset; unset purposes fall through to the
    deployment default. It cannot change *which* purpose a step runs under,
    which is what keeps routing off the wrong class of model."""

    decision: str | None = None
    answer: str | None = None


class ReplayRequestPayload(BaseModel):
    """ReplayRequestPayload"""

    since: int = 0


class ReplayRequestMessage(BaseModel):
    """Subscriber reconnected and wants the events it was not there for.

    Answered on the asking connection only, in order, each carrying its original
    sequence - so a caller that applies them cannot tell a replay from the first
    time, except that it asked."""

    action: Literal["replay_request"] = "replay_request"
    payload: ReplayRequestPayload
