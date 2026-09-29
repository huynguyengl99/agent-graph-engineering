import logging
from typing import Any

import structlog

from triage.core.config import settings


def setup_logging() -> None:
    """Readable lines while developing, JSON everywhere else."""
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(format="%(message)s", level=level)

    # ConsoleRenderer formats the traceback itself, so `format_exc_info` is
    # only added for the JSON path.
    render: list[Any] = (
        [structlog.dev.ConsoleRenderer()]
        if settings.debug
        else [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            *render,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
