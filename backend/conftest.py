"""Pytest configuration for backend tests."""

import shutil

from django.conf import settings

import pytest
from _pytest.main import Session


def pytest_sessionfinish(session: Session, exitstatus: int) -> None:
    """Clean up media files after successful test run."""
    if exitstatus != 0:
        return

    shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True, scope="session")
def redis_xdist(worker_id: str) -> None:
    """Create fresh Redis layers for each test worker (pytest-xdist support)."""
    # Clear all existing layers
    if worker_id == "master":
        wid = 0
    else:
        wid = int(worker_id.replace("gw", "")) % 16

    redis_host = f"redis://localhost:6379/{wid}"
    settings.REDIS_URL = redis_host
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [redis_host],
            },
        },
    }
