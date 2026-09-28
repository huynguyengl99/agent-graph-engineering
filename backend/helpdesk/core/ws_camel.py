"""Make the wire format match the generated AsyncAPI document.

chanx's `CHANX["CAMELIZE"]` only affects schema *generation*: the AsyncAPI
document declares `eventType` while the socket would still send `event_type`.
A client generated from that document then fails to find the fields it was
promised.

Camelizing in `encode_json` fixes it once, for every message on the consumer,
rather than per payload at each call site. Incoming frames are decamelized on
the way back so handlers keep working in snake_case.
"""

import json
from typing import Any

import humps


class CamelCaseJSONMixin:
    """Mix in before the chanx consumer base so these overrides win."""

    @classmethod
    async def encode_json(cls, content: Any) -> str:
        return json.dumps(humps.camelize(content))

    @classmethod
    async def decode_json(cls, text_data: str) -> Any:
        return humps.decamelize(json.loads(text_data))
