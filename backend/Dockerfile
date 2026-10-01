# Built from the repo root, because the uv lock is a workspace lock:
#   docker build -f backend/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /code

# Dependencies resolve from the workspace root, so both member manifests have to
# be present before the lock can be honoured. Copied on their own first, so a
# source change does not reinstall them.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
COPY agent/pyproject.toml agent/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package backend --no-install-workspace

COPY backend/ backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package backend


FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /code /code

ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=helpdesk.config.settings.base

WORKDIR /code/backend

# A key is needed to import settings for collectstatic; the real one arrives in
# the environment at run time.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --no-input

EXPOSE 8000

# ASGI, not WSGI: the ticket and conversation channels are WebSockets.
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", \
     "helpdesk.config.asgi:application"]
