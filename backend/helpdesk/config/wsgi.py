"""WSGI config for backend project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helpdesk.config.settings.dev")

application = get_wsgi_application()
