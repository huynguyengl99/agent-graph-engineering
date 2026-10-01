# Built from the repo root, because the uv lock is a workspace lock:
#   docker build -f agent/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /code

COPY pyproject.toml uv.lock ./
COPY agent/pyproject.toml agent/
COPY backend/pyproject.toml backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package agent --no-install-workspace

COPY agent/ agent/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package agent


FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /code /code

ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /code/agent

EXPOSE 8001

# No --reload: that watches the filesystem and restarts, which is a development
# convenience and a way to drop in-flight runs in production.
CMD ["uvicorn", "assistant.main:app", "--host", "0.0.0.0", "--port", "8001"]
