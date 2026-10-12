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

# Run tasks in-process. The queue is not what any of these tests are about, and
# a broker would make them depend on Redis being up.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
