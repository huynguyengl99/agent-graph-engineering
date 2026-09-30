# Agent Graph Engineering - justfile
# Install just: https://github.com/casey/just

# List all available commands
default:
    @just --list

# Install all dependencies (Python + Node)
install:
    @echo "📦 Installing dependencies..."
    uv sync
    cd web && pnpm install

# Start Docker infrastructure (PostgreSQL + Redis), waiting until it accepts
infra-up:
    @echo "🚀 Starting infrastructure..."
    docker compose up -d
    @bash scripts/wait-for-infra.sh

# Stop Docker infrastructure
infra-down:
    @echo "🛑 Stopping infrastructure..."
    docker compose down

# Run Django migrations
migrate:
    @echo "🔄 Running migrations..."
    cd backend && uv run python manage.py migrate

# Create Django migrations
makemigrations:
    @echo "🔄 Creating migrations..."
    cd backend && uv run python manage.py makemigrations

# Create Django superuser
createsuperuser:
    @echo "👤 Creating superuser..."
    cd backend && uv run python manage.py createsuperuser

# Generate agent → backend client (Python WebSocket client)
gen-agent-client:
    @echo "🔧 Generating agent client..."
    @bash scripts/dev.sh up a
    bash scripts/gen-agent-client.sh

# Generate backend → frontend (Zodios + TypeScript types)
gen-frontend:
    @echo "🔧 Generating frontend code..."
    @bash scripts/dev.sh up b
    cd web && pnpm gen:all

# Generate all code (agent + frontend)
gen: gen-agent-client gen-frontend

# Start backend server (Granian)
backend:
    @echo "🚀 Starting backend..."
    cd backend && uv run granian --interface asgi --port 8000 --reload helpdesk.config.asgi:application

# Start agent service (Uvicorn)
agent:
    @echo "🤖 Starting agent..."
    cd agent && uv run uvicorn assistant.main:app --port 8001 --reload

# Start frontend dev server (Vite)
frontend:
    @echo "💻 Starting frontend..."
    cd web && pnpm dev

# Start every service in the background, waiting until each answers (`just up a w` for a subset)
up *ARGS:
    @bash scripts/dev.sh up {{ARGS}}

# Stop the services `just up` started
down *ARGS:
    @bash scripts/dev.sh down {{ARGS}}

# Which services are up
status:
    @bash scripts/dev.sh status

# Follow a background service's log, e.g. `just logs a`
logs *ARGS:
    @bash scripts/dev.sh logs {{ARGS}}

# Run the backend, agent and web test suites
test:
    @echo "🧪 Running backend tests..."
    cd backend && uv run pytest
    @echo "🧪 Running agent tests..."
    cd agent && uv run pytest
    @echo "🧪 Running web tests..."
    cd web && pnpm test
    @echo "🧪 Running web tests..."
    cd web && pnpm test

# Run the eval golden set against the agent
evals *args:
    @echo "🎯 Running evals..."
    cd agent && uv run python -m evals.run {{args}}

# Diff two eval runs by label, e.g. `just evals-compare scripted openai_gpt-4o`
evals-compare before after:
    cd agent && uv run python -m evals.compare {{before}} {{after}}

# Seed a user and a couple of tickets for the end-to-end smoke
e2e-seed:
    @echo "🌱 Seeding e2e fixtures..."
    cd backend && uv run python manage.py seed_e2e

# End-to-end smoke: real services, real models, real browser (spends tokens)
e2e: e2e-seed
    @echo "🌐 Running the end-to-end smoke..."
    @bash scripts/dev.sh up
    cd web/e2e && npm install --silent && node smoke.mjs

# Run backend tests with coverage
test-cov:
    @echo "🧪 Running backend tests with coverage..."
    cd backend && uv run pytest --cov=helpdesk --cov-report=html

# Type check backend (mypy)
typecheck-backend:
    @echo "🔍 Type checking backend with mypy..."
    cd backend && uv run mypy .

# Type check with pyright (the second opinion; mypy is the first)
typecheck-pyright:
    @echo "🔍 Type checking with pyright..."
    cd backend && uv run pyright
    cd agent && uv run pyright

# Lint backend (ruff)
lint-backend:
    @echo "🔍 Linting backend..."
    cd backend && uv run ruff check .

# Fix backend linting issues
lint-fix-backend:
    @echo "🔧 Fixing backend linting..."
    cd backend && uv run ruff check --fix .

# Lint frontend
lint-frontend:
    @echo "🔍 Linting frontend..."
    cd web && pnpm lint

# Lint all workspaces
lint: lint-backend lint-frontend

# Fix all linting issues
lint-fix:
    @echo "🔧 Fixing all linting..."
    cd backend && uv run ruff check --fix .
    cd web && pnpm lint:fix

# Format backend (ruff)
format-backend:
    @echo "🎨 Formatting backend..."
    cd backend && uv run ruff format .

# Format all
format:
    @echo "🎨 Formatting all..."
    pnpm format

# Validate the OpenAPI schema (fails on any warning)
check-schema:
    @echo "🔍 Validating OpenAPI schema..."
    cd backend && uv run python manage.py spectacular --validate --fail-on-warn > /dev/null

# Every project's checks in parallel, reporting all failures at once (`just check ba`, `-e w`)
check *ARGS:
    @bash scripts/check.sh {{ARGS}}

# Apply every formatter and auto-fixable lint, then re-check
fix:
    @bash scripts/check.sh --fix

# Clean generated files and caches
clean:
    @echo "🧹 Cleaning..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
    rm -rf web/src/schemas/backend
    rm -rf web/src/types/backend
    rm -rf web/src/types/websocket
    rm -rf backend/helpdesk/agent_client

# Setup pre-commit hooks
pre-commit-install:
    @echo "🪝 Installing pre-commit hooks..."
    cd backend && uv pip install pre-commit && uv run pre-commit install

# Run pre-commit on all files
pre-commit:
    @echo "🪝 Running pre-commit..."
    cd backend && uv run pre-commit run --all-files

# Everything a fresh clone needs: .env, dependencies, infrastructure, schema, clients
setup: env install infra-up migrate gen
    @echo ""
    @echo "✅ Setup complete. Next:"
    @echo "     just createsuperuser   # someone to log in as"
    @echo "     just up                # all three services"
    @echo ""
    @echo "   The agent runs on a scripted model until OPENAI_API_KEY is set in .env."

# Create .env from the example, if it is not there yet
env:
    #!/usr/bin/env bash
    if [ -f .env ]; then
      echo "🔑 .env already exists, leaving it alone"
    else
      cp .env.example .env
      echo "🔑 wrote .env from .env.example"
    fi

# Development workflow: start all services
dev:
    @echo "🚀 Starting all services..."
    @echo "Run these in separate terminals:"
    @echo "  Terminal 1: just backend"
    @echo "  Terminal 2: just agent"
    @echo "  Terminal 3: just frontend"

# Quick start guide
help:
    @echo "Agent Graph Engineering - Quick Commands"
    @echo ""
    @echo "Setup (first time):"
    @echo "  just setup           - Complete setup (install, infra, migrate, gen)"
    @echo ""
    @echo "Development:"
    @echo "  just backend         - Start backend (port 8000)"
    @echo "  just agent           - Start agent (port 8001)"
    @echo "  just frontend        - Start frontend (port 5173)"
    @echo ""
    @echo "Code Generation:"
    @echo "  just gen             - Generate all code"
    @echo "  just gen-frontend    - Generate frontend only"
    @echo "  just gen-agent-client - Generate agent client only"
    @echo ""
    @echo "Testing & Quality:"
    @echo "  just test            - Run tests"
    @echo "  just lint            - Lint all code"
    @echo "  just check           - Run all checks"
    @echo ""
    @echo "For full list: just --list"
