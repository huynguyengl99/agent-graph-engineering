"""Schema preprocessing hooks for drf-spectacular."""
from .force_discriminator_required import force_discriminator_required_hook

__all__ = ["force_discriminator_required_hook"]
