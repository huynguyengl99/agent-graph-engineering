"""Model selection has two axes, and they must not bleed into each other.

The purpose a step runs under is the system's call. The model filling that
purpose is the user's. A user override must move every step sharing that
purpose and nothing else.
"""

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.factory import model_settings
from assistant.graphs.triage_graph import TriageGraph


def test_defaults_put_routing_on_the_cheap_model() -> None:
    config = AgentConfig.resolve()
    assert config.for_purpose(ModelPurpose.DECISION).slug == "openai:gpt-4o-mini"
    assert config.for_purpose(ModelPurpose.ANSWER).slug == "openai:gpt-4o"


def test_a_user_override_moves_only_its_own_purpose() -> None:
    config = AgentConfig.resolve(
        {ModelPurpose.DECISION: ModelConfig(provider="anthropic", name="claude-haiku-4-5")}
    )

    assert config.for_purpose(ModelPurpose.DECISION).slug == "anthropic:claude-haiku-4-5"
    # Untouched slots still fall through to the deployment default.
    assert config.for_purpose(ModelPurpose.ANSWER).slug == "openai:gpt-4o"


def test_steps_are_bound_to_purposes_not_models() -> None:
    graph = TriageGraph(
        AgentConfig.resolve(
            {ModelPurpose.DECISION: ModelConfig(provider="anthropic", name="claude-haiku-4-5")}
        )
    )

    # Classification and routing are decisions; customer prose is not.
    assert graph.classifier.purpose is ModelPurpose.DECISION
    assert graph.decider.purpose is ModelPurpose.DECISION
    assert graph.answerer.purpose is ModelPurpose.ANSWER


def test_config_does_not_change_the_topology() -> None:
    cheap = TriageGraph(AgentConfig.resolve())
    swapped = TriageGraph(
        AgentConfig.resolve(
            {ModelPurpose.ANSWER: ModelConfig(provider="anthropic", name="claude-opus-4-5")}
        )
    )
    assert sorted(cheap.nodes()) == sorted(swapped.nodes())


class TestModelSettings:
    """Knobs are spelled differently per provider, and one of them 400s."""

    def test_nothing_is_sent_when_nothing_is_set(self) -> None:
        assert model_settings(ModelConfig(provider="openai", name="gpt-4o")) is None

    def test_effort_uses_each_provider_s_own_name(self) -> None:
        anthropic = model_settings(
            ModelConfig(provider="anthropic", name="claude-sonnet-5", effort="low")
        )
        openai = model_settings(
            ModelConfig(provider="openai", name="gpt-5.2", effort="low")
        )

        assert anthropic == {"anthropic_effort": "low"}
        assert openai == {"openai_reasoning_effort": "low"}

    def test_temperature_is_absent_unless_asked_for(self) -> None:
        """Current Anthropic models reject `temperature` with a 400, so a
        default value would break every Claude run."""
        settings = model_settings(
            ModelConfig(provider="anthropic", name="claude-sonnet-5")
        )

        assert settings is None

    def test_temperature_is_sent_when_set(self) -> None:
        settings = model_settings(
            ModelConfig(provider="openai", name="gpt-4o", temperature=0.7)
        )

        assert settings == {"temperature": 0.7}

    def test_an_unknown_provider_drops_effort_rather_than_guessing(self) -> None:
        settings = model_settings(
            ModelConfig(provider="somebody-else", name="x", effort="max")
        )

        assert settings is None
