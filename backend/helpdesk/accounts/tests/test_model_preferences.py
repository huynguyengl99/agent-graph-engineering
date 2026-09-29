"""A user picks the model; the system keeps the purpose.

The value of this axis is that it actually reaches the agent, so these cover
the round trip rather than just the table.
"""

from helpdesk.accounts.factories import UserFactory
from helpdesk.accounts.models import ModelPreference, ModelPurpose
from helpdesk.accounts.services.preferences import overrides_for
from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase


class TestModelPreferenceApi(AuthAPITestCase):
    def test_a_choice_is_stored_per_purpose(self) -> None:
        response = self.auth_client.post(
            "/api/preferences/model-preferences/",
            {"purpose": "decision", "model": "anthropic:claude-haiku-4-5"},
            format="json",
        )

        assert response.status_code == 201
        assert ModelPreference.objects.filter(user=self.user).count() == 1

    def test_choosing_again_replaces_rather_than_duplicates(self) -> None:
        for model in ("openai:gpt-4o-mini", "anthropic:claude-haiku-4-5"):
            self.auth_client.post(
                "/api/preferences/model-preferences/",
                {"purpose": "decision", "model": model},
                format="json",
            )

        preferences = ModelPreference.objects.filter(user=self.user)
        assert preferences.count() == 1
        assert preferences.first().model == "anthropic:claude-haiku-4-5"  # type: ignore[union-attr]

    def test_a_bare_model_name_is_rejected(self) -> None:
        """Without a provider the agent silently uses whichever is default."""
        response = self.auth_client.post(
            "/api/preferences/model-preferences/",
            {"purpose": "answer", "model": "gpt-4o"},
            format="json",
        )

        assert response.status_code == 400

    def test_you_only_see_your_own(self) -> None:
        other = self.get_client_for_user(UserFactory.create())
        other.post(
            "/api/preferences/model-preferences/",
            {"purpose": "answer", "model": "openai:gpt-4o"},
            format="json",
        )

        response = self.auth_client.get("/api/preferences/model-preferences/")
        assert response.json()["count"] == 0


class TestOverridesReachTheAgent(AuthAPITestCase):
    """`overrides_for` is what the services hand to the agent."""

    def test_only_chosen_purposes_are_sent(self) -> None:
        """Unset purposes are absent, not null: the agent falls through to its
        own default rather than interpreting an empty value."""
        ModelPreference.objects.create(
            user=self.user,
            purpose=ModelPurpose.DECISION,
            model="anthropic:claude-haiku-4-5",
        )

        overrides = overrides_for(self.user.pk)

        assert overrides == {"decision": "anthropic:claude-haiku-4-5"}

    def test_no_preferences_sends_nothing(self) -> None:
        assert overrides_for(self.user.pk) == {}

    def test_an_anonymous_caller_sends_nothing(self) -> None:
        assert overrides_for(None) == {}
