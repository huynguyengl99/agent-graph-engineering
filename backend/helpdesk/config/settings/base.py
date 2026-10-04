"""Base settings for backend project."""

from pathlib import Path

import structlog
from environs import Env

env = Env()
env.read_env()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security
SECRET_KEY = env.str("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", [])

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third party
    "rest_framework",
    "auth_kit",
    "allauth",
    "allauth.account",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "polymorphic",
    "chanx.channels",
    "drf_standardized_errors",
    "django_structlog",
    # Local
    "helpdesk.accounts",
    "helpdesk.core",
    "helpdesk.tickets",
]

# Required for allauth
SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, so every log line inside a request carries its request_id and user_id.
    "django_structlog.middlewares.RequestMiddleware",
]

ROOT_URLCONF = "helpdesk.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "helpdesk.config.wsgi.application"
ASGI_APPLICATION = "helpdesk.config.asgi.application"

# Database
DATABASES = {
    "default": env.dj_db_url(
        "DATABASE_URL",
        default="postgresql://postgres:postgres@localhost:5432/triage_dev",
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# CORS
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
CORS_ALLOW_CREDENTIALS = True

# Browsers send `Origin` on form posts, and Django checks it against this for
# any session-authenticated POST. Behind a reverse proxy the app's origin is not
# the one Django sees itself on, so without this the admin login fails with a
# bare "CSRF verification failed" - and it fails only in a browser, because curl
# sends no Origin at all.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    ["http://localhost:5173", "http://localhost:8000"],
)

# WebSocket Origin check. Defaults to the same origins the REST API trusts;
# set "*" only in local development.
WEBSOCKET_ALLOWED_ORIGINS = env.list(
    "WEBSOCKET_ALLOWED_ORIGINS",
    CORS_ALLOWED_ORIGINS,
)

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env.str("REDIS_URL", "redis://localhost:6379/0")],
        },
    },
}

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Matches the cookie auth_kit issues on login. Session auth stays for
        # the Django admin and the browsable API.
        "auth_kit.authentication.JWTCookieAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "djangorestframework_camel_case.render.CamelCaseJSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "djangorestframework_camel_case.parser.CamelCaseJSONParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "drf_standardized_errors.handler.exception_handler",
}

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Agent Graph Engineering API",
    "DESCRIPTION": "Schema-first fullstack reference with polymorphic serialization",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CAMELIZE_NAMES": True,
    "COMPONENT_SPLIT_REQUEST": True,
    # The discriminator hook rewrites generated components, so it has to run
    # after generation. Registered as a preprocessing hook it gets called with
    # `endpoints=` and raises.
    # Order matters. Camelize runs first, on the serializer-shaped components it
    # understands, so the schema matches what CamelCaseJSONRenderer puts on the
    # wire. The discriminator hook then flattens the polymorphic variants and
    # renames the discriminator to match. Reversed, camelize skips the variants
    # because the hook has already replaced them with plain objects.
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "drf_spectacular.contrib.djangorestframework_camel_case.camelize_serializer_fields",
        "helpdesk.core.schema_hooks.force_discriminator_required_hook",
    ],
    # `status`, `old_status` and `new_status` all draw on TicketStatus, which
    # spectacular would otherwise name three different ways.
    "ENUM_NAME_OVERRIDES": {
        "TicketStatusEnum": "helpdesk.tickets.models.ticket.TicketStatus.choices",
    },
    "SCHEMA_PATH_PREFIX": "/api",
}

# Chanx
CHANX = {
    "CAMELIZE": True,
}

# Auth Kit (drf-auth-kit)
AUTH_KIT = {
    "USER_SERIALIZER": "helpdesk.accounts.serializers.UserSerializer",
    "REGISTRATION_ENABLED": True,
    "LOGIN_CREDENTIAL_FIELDS": ["email"],
    # The key is AUTH_TYPE, not USE_JWT. The old `"USE_JWT": False` was a no-op,
    # so auth_kit kept its jwt default and set JWT cookies that DRF (configured
    # for SessionAuthentication only) rejected: every call after login was 403.
    # DRF now accepts that cookie. `"session"` would need a custom
    # LOGIN_RESPONSE_SERIALIZER, so jwt stays.
    "AUTH_TYPE": "jwt",
}

# Logging
# structlog renders; the stdlib stays as the transport so Django's own loggers
# come out in the same shape.
STRUCTLOG_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
]

structlog.configure(
    processors=[
        *STRUCTLOG_PROCESSORS,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=DEBUG),
            ],
            "foreign_pre_chain": STRUCTLOG_PROCESSORS,
        },
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            "foreign_pre_chain": STRUCTLOG_PROCESSORS,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console" if DEBUG else "json",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            # django_structlog already logs every request with more context.
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# Agent service
AGENT_WS_URL = env.str("AGENT_WS_URL", "ws://localhost:8001")
# Shared with the agent, which rejects the handshake without it. Empty on both
# sides means an unauthenticated agent, which only holds while nothing but this
# service can reach it.
AGENT_TOKEN = env.str("ASSISTANT_AGENT_TOKEN", "")
# Tests drive the triage client explicitly; leaving the automatic
# trigger on would make results depend on whether the agent is running.
TRIAGE_ON_COMMENT = env.bool("TRIAGE_ON_COMMENT", True)

# How long one run may hold a ticket's lane before another may take it over. A
# run parked on a person holds it for as long as they take, so this only has to
# outlast the agent working, not a reviewer deciding.
AGENT_RUN_CLAIM_TIMEOUT = env.int("AGENT_RUN_CLAIM_TIMEOUT", 300)
AGENT_ANSWER_MODEL = env.str("TRIAGE_ANSWER_MODEL", "gpt-4o")
