"""Development settings."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Only so `runserver` speaks ASGI. It is a dev dependency, and listing it in the
# base settings meant a production install could not import them at all: granian
# serves ASGI without it.
INSTALLED_APPS = ["daphne", *INSTALLED_APPS]  # noqa: F405

# Allow all CORS in development
CORS_ALLOW_ALL_ORIGINS = True
