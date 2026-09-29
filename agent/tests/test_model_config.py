"""Model selection has two axes, and they must not bleed into each other.

The purpose a step runs under is the system's call. The model filling that
purpose is the user's. A user override must move every step sharing that
purpose and nothing else.
"""

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
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
