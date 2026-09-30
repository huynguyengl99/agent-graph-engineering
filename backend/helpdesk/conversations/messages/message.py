"""One conversation turn, as it travels over the WebSocket.

Mirrors `MessageSerializer`, and `serialize_message` builds it *from* that
serializer rather than beside it. A message reaches the browser two ways - the
REST page load and the realtime feed - and the two used to disagree: the feed
declared its own `{id, role, content, created_at}`, and `assistant_done`
declared a third shape again, `{message_id, content}`, which left the client
inventing a timestamp for a row the database had already stamped.
"""

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A persisted turn. The same shape the REST endpoint returns."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
