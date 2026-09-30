"""Development settings."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Allow all CORS in development
CORS_ALLOW_ALL_ORIGINS = True
