from fast_channels.layers import (
    BaseChannelLayer,
    InMemoryChannelLayer,
    has_layers,
    register_channel_layer,
)

from triage.core.config import settings

LAYER_ALIAS = "triage"


def setup_layers(force: bool = False) -> None:
    if has_layers() and not force:
        return

    layer: BaseChannelLayer
    if settings.redis_url:
        from fast_channels.layers.redis import RedisPubSubChannelLayer

        layer = RedisPubSubChannelLayer(hosts=[settings.redis_url], prefix=LAYER_ALIAS)
    else:
        # Single-process default; set REDIS_URL to scale across workers.
        layer = InMemoryChannelLayer()

    register_channel_layer(LAYER_ALIAS, layer)
