"""Traces, proxied from the agent behind staff auth.

The agent renders the page because it owns the spans; this adds the two things
it cannot: an authenticated URL, and a reachable one. The agent is internal and
answers only with the shared token, so the browser never talks to it directly.

In the admin rather than the React app because a trace is an operator's tool. A
support agent has no use for a span tree.
"""

from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import path, reverse
from rest_framework import status

import httpx

from helpdesk.core.agent_connection import agent_headers

TRACES_BASE = "/admin/observability/trace"

NAV = """
<div style="background:#417690;padding:10px 20px;font:13px -apple-system,
BlinkMacSystemFont,'Segoe UI',sans-serif;display:flex;gap:12px">
  <a href="{admin}" style="color:#fff;text-decoration:none">&larr; Admin</a>
  <span style="color:rgba(255,255,255,.5)">|</span>
  <a href="{dashboard}" style="color:rgba(255,255,255,.85);text-decoration:none">Traces</a>
</div>
"""


def _with_nav(html: str) -> str:
    nav = NAV.format(
        admin=reverse("admin:index"), dashboard=reverse("admin:trace_dashboard")
    )
    return html.replace("<body>", f"<body>{nav}", 1)


def _fetch(path_suffix: str) -> httpx.Response:
    return httpx.get(
        f"{settings.AGENT_HTTP_URL}/traces{path_suffix}",
        params={"base": TRACES_BASE},
        headers=agent_headers(),
        timeout=10,
    )


def _proxy(path_suffix: str) -> HttpResponse:
    url = f"{settings.AGENT_HTTP_URL}/traces{path_suffix}"
    try:
        response = _fetch(path_suffix)
    except httpx.HTTPError as error:
        # Said, not swallowed: this page exists to explain what happened, so
        # answering with an empty one is the least useful thing it could do.
        return HttpResponse(
            f"Could not reach the agent at {url}: {error}",
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        return HttpResponse(
            "The agent rejected this request. Check ASSISTANT_AGENT_TOKEN "
            "matches on both sides.",
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if not response.is_success:
        return HttpResponse(
            f"The agent answered {response.status_code} for {url}.",
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return HttpResponse(_with_nav(response.text))


def trace_dashboard(_request: HttpRequest) -> HttpResponse:
    return _proxy("/dashboard")


def trace_detail(_request: HttpRequest, run_id: str) -> HttpResponse:
    return _proxy(f"/{run_id}/html")


def trace_asset(_request: HttpRequest, asset: str) -> HttpResponse:
    """The page is served from here, so its stylesheet is requested from here.

    Only the two files the templates reference: this is an authenticated hole
    through to an internal service, not a general-purpose proxy.
    """
    if asset not in ("trace.css", "trace.js"):
        return HttpResponse("Not found.", status=status.HTTP_404_NOT_FOUND)

    try:
        response = _fetch(f"/static/{asset}")
    except httpx.HTTPError as error:
        return HttpResponse(
            f"Could not reach the agent: {error}",
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not response.is_success:
        return HttpResponse(
            f"The agent answered {response.status_code}.",
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return HttpResponse(
        response.content,
        content_type=response.headers.get("content-type", "text/plain"),
    )


class ObservabilityAdminSite(admin.AdminSite):
    def get_urls(self) -> list[Any]:
        return [
            path(
                "observability/trace/dashboard/",
                self.admin_view(trace_dashboard),
                name="trace_dashboard",
            ),
            path(
                "observability/trace/static/<str:asset>",
                self.admin_view(trace_asset),
                name="trace_asset",
            ),
            path(
                "observability/trace/<str:run_id>/html",
                self.admin_view(trace_detail),
                name="trace_detail",
            ),
        ] + super().get_urls()

    def get_app_list(
        self, request: HttpRequest, app_label: str | None = None
    ) -> list[dict[str, Any]]:
        app_list = super().get_app_list(request, app_label)
        if app_label not in (None, "observability"):
            return app_list

        app_list.append(
            {
                "name": "Observability",
                "app_label": "observability",
                "app_url": reverse("admin:trace_dashboard"),
                "has_module_perms": True,
                "models": [
                    {
                        "name": "Traces",
                        "object_name": "Trace",
                        "admin_url": reverse("admin:trace_dashboard"),
                        "view_only": True,
                    }
                ],
            }
        )
        return app_list


admin.site.__class__ = ObservabilityAdminSite
