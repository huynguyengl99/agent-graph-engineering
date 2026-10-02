from typing import Any

from assistant.core.layers import LAYER_ALIAS


class NoSocket:
    """Stands in for the hub consumer, so a topic can be built without one.

    A real topic rather than a subclass: chanx namespaces a group by the concrete
    class name, so a test subclass would publish where nothing is listening.
    """

    scope: dict[str, Any] = {}
    channel_name = "test-channel"
    channel_layer = None
    channel_layer_alias = LAYER_ALIAS
    should_camelize = False

    async def send_topic_json(self, topic: str, content: dict[str, Any]) -> None:
        pass
