"""Traces reach a staff user and nobody else, and a dead agent says so."""

from unittest.mock import patch

from django.test import override_settings

import httpx

from helpdesk.accounts.factories import UserFactory
from helpdesk.core.agent_connection import TOKEN_HEADER
from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase

DASHBOARD = "/admin/observability/trace/dashboard/"
DETAIL = "/admin/observability/trace/run-1/html"
ASSET = "/admin/observability/trace/static/trace.css"

PAGE = "<html><body><h1>Traces</h1></body></html>"


def ok(content: str = PAGE, content_type: str = "text/html") -> httpx.Response:
    return httpx.Response(200, text=content, headers={"content-type": content_type})


class TestAccess(AuthAPITestCase):
    def test_anonymous_is_sent_to_the_login_page(self) -> None:
        self.client.logout()

        assert self.client.get(DASHBOARD).status_code == 302

    def test_a_non_staff_user_cannot_read_traces(self) -> None:
        plain = UserFactory.create(is_staff=False)
        self.client.force_login(plain)

        # Django's admin sends a non-staff user to the login page rather than
        # answering, which is the behaviour we want to inherit.
        assert self.client.get(DASHBOARD).status_code in (302, 403)


@override_settings(AGENT_HTTP_URL="http://agent:8001", AGENT_TOKEN="s3cret")
class TestProxy(AuthAPITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.auth_client.force_login(self.user)

    def test_the_page_comes_through_with_a_nav_bar(self) -> None:
        with patch("helpdesk.observability.admin.httpx.get", return_value=ok()):
            response = self.auth_client.get(DASHBOARD)

        assert response.status_code == 200
        assert b"Traces" in response.content
        assert b"Admin" in response.content, "the nav bar was not injected"

    def test_the_agent_is_told_who_is_asking(self) -> None:
        with patch("helpdesk.observability.admin.httpx.get", return_value=ok()) as get:
            self.auth_client.get(DETAIL)

        sent = get.call_args.kwargs
        assert sent["headers"][TOKEN_HEADER] == "s3cret"
        # `base` is what makes the agent's links resolve under /admin/.
        assert sent["params"]["base"] == "/admin/observability/trace"

    def test_an_unreachable_agent_says_so(self) -> None:
        """A page whose job is explaining what happened must not answer blank."""
        with patch(
            "helpdesk.observability.admin.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            response = self.auth_client.get(DASHBOARD)

        assert response.status_code == 502
        assert b"Could not reach the agent" in response.content

    def test_a_rejected_token_names_the_setting(self) -> None:
        with patch(
            "helpdesk.observability.admin.httpx.get",
            return_value=httpx.Response(401),
        ):
            response = self.auth_client.get(DASHBOARD)

        assert response.status_code == 502
        assert b"ASSISTANT_AGENT_TOKEN" in response.content

    def test_the_stylesheet_keeps_its_content_type(self) -> None:
        with patch(
            "helpdesk.observability.admin.httpx.get",
            return_value=ok("body{}", "text/css"),
        ):
            response = self.auth_client.get(ASSET)

        assert response.status_code == 200
        assert response["content-type"] == "text/css"

    def test_nothing_but_the_two_assets_is_proxied(self) -> None:
        """An authenticated hole through to an internal service, not a general
        purpose proxy."""
        response = self.auth_client.get(
            "/admin/observability/trace/static/..%2Fsecrets"
        )

        assert response.status_code == 404
