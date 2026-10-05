"""Test settings."""

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = "test-secret-key-long-enough-for-hmac-sha256"  # noqa: S105
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Origin policy is an integration concern; these tests exercise consumers.
WEBSOCKET_ALLOWED_ORIGINS = ["*"]

AGENT_ON_COMMENT = False

# Marks the end of a handler's output so receive_all_messages() can stop reading.
CHANX = {**CHANX, "SEND_COMPLETION": True}  # noqa: F405

# Use in-memory channel layer for tests
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Faster password hashing for tests
AUTH_PASSWORD_VALIDATORS = []
