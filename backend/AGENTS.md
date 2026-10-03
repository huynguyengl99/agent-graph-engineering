# Backend - Agent Instructions

**IMPORTANT**: When the user corrects you about a convention, pattern, structure, coding style, or gotcha — update this AGENTS.md to capture it so the lesson persists across sessions.

## Project Structure

```
backend/
├── helpdesk/                 # Main Django project
│   ├── manage.py
│   ├── config/                  # Settings (base/dev), URLs, ASGI → app configuration
│   ├── accounts/                # Auth (drf-auth-kit), user profiles → user/auth features
│   ├── tickets/                 # Ticket system with polymorphic events → core domain
│   │   ├── models/
│   │   │   ├── ticket.py        # Ticket model
│   │   │   └── events/          # Polymorphic event models (comment, status_change, assignment, ai_response)
│   │   ├── serializers/
│   │   │   └── event.py         # PolymorphicSerializer — THE CONTRACT
│   │   ├── views/
│   │   ├── consumers/           # WebSocket consumers (chanx)
│   │   ├── routing.py           # WebSocket routing
│   │   └── urls.py
│   ├── core/                    # Shared utilities, base models, schema hooks
│   │   ├── services/
│   │   │   └── support_run.py   # One connection to the agent; a `Sink` writes it down
│   │   └── schema_hooks/        # OpenAPI discriminator hooks for drf-spectacular
│   ├── test_utils/              # BaseModelFactory, test helpers → test infrastructure
│   ├── agent_client/            # ⚠️ GENERATED — DO NOT EDIT (run just gen-agent-client)
│   └── templates/               # Django templates
├── pyproject.toml               # Dependencies (uv)
├── mypy.ini                     # Type checking config
├── ruff.toml                    # Linter config
└── pyrightconfig.json           # Pyright config
```

## Quick Commands

```bash
# Install dependencies
uv sync

# Development server (Granian ASGI server with WebSocket support)
just backend
# Or directly:
cd backend && uv run granian --interface asgi --port 8000 --reload helpdesk.config.asgi:application

# Database
just makemigrations
just migrate

# Linting & type checking
cd backend && uv run ruff check .     # Ruff linter
cd backend && uv run mypy .           # mypy type checker
cd backend && pyright                  # Pyright type checker

# Tests
just test                              # All tests
just test-cov                          # With coverage
```

## Code Style

- Follow PEP 8 with 88 char line length (Ruff/Black formatting)
- Use type hints on all function signatures, models, serializers, views/viewsets, admin classes, etc. Always use concrete generic type hints (e.g., `BaseModelFactory[MyModel]`, `ModelSerializer[MyModel]`, `ModelViewSet[MyModel]`)
- **HARD CONSTRAINT - Imports at top of file**: Always place imports at the top of the file, never inline inside functions. The only exceptions are:
  - Inside `if TYPE_CHECKING:` blocks (for type-only imports)
  - When Django/server startup actually fails due to circular imports (very rare — only if `manage.py check` or `runserver` complains)
- Prefer Django ORM over raw SQL
- Use Django REST Framework serializers for API I/O
- Async-first for I/O-bound operations in Channels
- Only run linting/formatting/typechecking at the end of a feature implementation or bug fix, not after every small change. Stay calm and batch it.

### Django Admin

- Always use `autocomplete_fields` for ForeignKey and ManyToManyField in admin classes
- Always use `select_related` / `prefetch_related` via `list_select_related` or `get_queryset()` for list views in admin

### Django Polymorphic

This project uses `django-polymorphic` + `django-rest-polymorphic` for models with type hierarchies:

- `helpdesk/tickets/models/events/` — Ticket event types (Comment, StatusChange, Assignment, AIResponse)

Reference these when working with polymorphic patterns.

## API Development

### Adding a new endpoint

1. Create/update views in `helpdesk/<app>/views.py`
2. Create/update serializers in `helpdesk/<app>/serializers.py`
3. Register URLs in `helpdesk/<app>/urls.py`
4. Frontend regenerates client with `just gen-frontend`

### Adding a new model

1. Define model in `helpdesk/<app>/models.py`
2. Create migration: `just makemigrations`
3. Apply migration: `just migrate` (only when user asks)

## Generated Code - DO NOT EDIT

- `helpdesk/agent_client/` - WebSocket client for agent communication (from Agent AsyncAPI)

**Regenerate**: `just gen-agent-client` (agent must be running at :8001)

## Testing

```bash
just test                                        # All tests
just test-cov                                    # With coverage
cd backend && uv run pytest helpdesk/tickets/ # Single app
```

Run tests when the user explicitly asks, or when a feature/fix is complete. No need to run after every small change.

### Factories

Use `BaseModelFactory` from `helpdesk/test_utils/model_factory.py` for all test factories. It provides:

- **Generic type hints** for pyright/mypy (e.g., `BaseModelFactory[MyModel]` — `create()` returns `MyModel`)
- **Async support** via `acreate()`
- **Auto Meta.model** from the generic type argument (no need to define `Meta.model` manually)

## WebSocket (Chanx + Channels)

- Uses **chanx** (abstraction over Django Channels) for WebSocket consumers
- Consumers in `helpdesk/<app>/consumers/`
- Routing in `helpdesk/<app>/routing.py`
- ASGI config in `helpdesk/config/asgi.py`
- AsyncAPI schema auto-generated at `/api/asyncapi/schema/`

## Warnings & Gotchas

1. **Agent client is generated**: Never manually edit `helpdesk/agent_client/`
2. **ASGI server required**: Use Granian or Uvicorn (not runserver) for WebSocket support — `just backend`. Daphne is available as dev dependency.
3. **Never run `migrate` automatically**: Never run migrations unless the user explicitly asks. Running `makemigrations` is OK.
4. **WebSocket via Chanx + Channels**: Use Chanx (not raw Django Channels consumers)
5. **No venv activation**: The user already has the virtualenv activated. Never run `source .venv/bin/activate` or similar.
6. **CharField with choices naming**: Don't name the field the same as the choice enum. Use descriptive names with context (e.g., `ticket_status`) instead of generic names (e.g., `status`) to avoid naming collisions.
7. **Type casting request.user**: Use `cast(User, request.user)` instead of `# type: ignore[assignment]` in views.

## Topics, not one consumer per resource

Every browser tab opens a single socket at `/ws/` (`core/consumers/hub.py`).
Tickets and conversations are *topics* on it, addressed per frame:

- `ticket:{ticket_id}` - customer-visible, so sending a reply is gated
- `conversation:{conversation_id}` - the rep's own thread, gated only on the
  way out via `draft_to_ticket`

Two reasons this is not just tidier. `Topic.broadcast` is a **classmethod**, so
a detached task with no consumer instance can publish directly - the old
`broadcast()` helper hand-rolled that envelope and existed in two copies. And
one socket serves however many resources a tab is watching, instead of one
connection and one auth round-trip each.

`authorize()` on the topic is where access control lives: an unknown ticket or
someone else's conversation is refused at subscribe, not at connect.

Note for tests: a topic fan-out terminates with `event_complete`, while a
handler's own reply terminates with `complete`. `receive_topic_messages` in
`test_utils/websocket.py` reads one fan-out at a time and parses against the
topic's output union, because the communicator parses against the *consumer's*.


## Talking to the agent

One relay, `core/services/support_run.py`. It opens the connection, subscribes
to `support:<audience>:<thread_id>`, replays what it missed, moves the cursor
and disconnects - and hands every event to a `Sink`.

| Sink | Writes to | Visibility |
|---|---|---|
| `tickets/services/support.py` | ticket events | the audience's: public for a customer's run, internal for the team's |
| `conversations/services/chat.py` | conversation messages | there is no customer here, so nothing is gated |

There were three relays: a ticket's customer run, a ticket's team run, and a
conversation. They talked identically and differed only in what they wrote down,
which is why the talking is one class and the writing-down is three methods.

The ticket's two audiences are **one sink**: the visibility an answer is filed
under is the whole difference between drafting for the customer behind the gate
and answering the lane the team asked in.

### Visibility is enforced twice

The REST list filters internal events out for non-staff, and the topic's event
handlers filter **per subscriber** - an internal note, the agent's reasoning and
an unapproved draft all reached a customer who had the ticket open until the
second one existed. Scoping the queryset is not enough when it is their ticket:
`PATCH /api/tickets/{id}/` refuses a non-staff writer too.
