# Backend - Agent Graph Engineering

## Type Checking & Linting

This project uses **both mypy and pyright** for comprehensive type checking:

### Mypy (Django-specific)
```bash
# Check all code
uv run mypy .

# Check specific app
uv run mypy helpdesk/tickets

# Check specific file
uv run mypy helpdesk/tickets/models/ticket.py
```

Configuration: `mypy.ini`
- Strict mode enabled
- Django plugin configured
- Ignore missing imports for third-party packages without stubs

### Pyright (General Python)
```bash
# Check with pyright (if installed globally)
pyright

# Or use VSCode Python extension (uses pyrightconfig.json automatically)
```

Configuration: `pyrightconfig.json`
- Strict type checking mode
- Configured for Django settings

### Ruff (Linting + Formatting)
```bash
# Lint code
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check --fix .

# Format code (if using ruff format)
uv run ruff format .
```

Configuration: `ruff.toml`
- Comprehensive rule set
- Django-specific rules enabled
- Isort configuration for import sorting

## Running Checks

### Before Commit
```bash
# Run all checks
uv run mypy .
uv run ruff check .
uv run python manage.py check

# Run tests
uv run pytest
```

### In VSCode
Install extensions:
- Python (ms-python.python) - uses pyrightconfig.json
- Mypy Type Checker (ms-python.mypy-type-checker)
- Ruff (charliermarsh.ruff)

All three will run automatically with the project configurations.

## Configuration Files

| File | Purpose |
|------|---------|
| `mypy.ini` | Mypy type checking with Django plugin |
| `pyrightconfig.json` | Pyright strict type checking |
| `ruff.toml` | Ruff linting/formatting with Django rules |
| `pyproject.toml` | Dependencies & metadata |
