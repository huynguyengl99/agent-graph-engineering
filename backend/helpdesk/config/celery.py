"""The Celery app. The settings that matter are in `settings/base.py`."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helpdesk.config.settings.dev")

app = Celery("helpdesk")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
