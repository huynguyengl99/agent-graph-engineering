"""Asking a run to say again what a subscriber missed."""

from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


class ReplayRequestPayload(BaseModel):
    # The last sequence the caller has already handled. 0 means "everything".
    since: int = 0


class ReplayRequestMessage(BaseMessage):
    """Subscriber reconnected and wants the events it was not there for.

    Answered on the asking connection only, in order, each carrying its original
    sequence - so a caller that applies them cannot tell a replay from the first
    time, except that it asked.
    """

    action: Literal["replay_request"] = "replay_request"
    payload: ReplayRequestPayload
