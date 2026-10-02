from typing import Literal

from pydantic import BaseModel


class PingMessage(BaseModel):
    """Simple ping message to check WebSocket connection status."""

    action: Literal["ping"] = "ping"
    payload: None = None


class PongMessage(BaseModel):
    """Simple pong message response to ping requests."""

    action: Literal["pong"] = "pong"
    payload: None = None


IncomingMessage = PongMessage
OutgoingMessage = PingMessage
