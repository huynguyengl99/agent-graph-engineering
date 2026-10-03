"""The harness itself.

An eval suite that passes while the thing it tests is broken is worse than no
suite, so these cover the scoring rather than the agent.
"""

from pathlib import Path

import pytest
from assistant.guardrails import Finding, Severity, kind_of
from evals.core.runner import Observation
from evals.core.scenario import Expect, load_scenarios
from evals.core.scoring import score

SCENARIOS = Path(__file__).parent.parent / "evals" / "scenarios"


def observation(**kwargs: object) -> Observation:
    return Observation(**kwargs)  # type: ignore[arg-type]


def test_kind_survives_a_render_round_trip() -> None:
    """scoring parses what render produces; they must not drift apart."""
    finding = Finding(kind="fake_authority", severity=Severity.NOTICE, detail="x: y")
    assert kind_of(finding.render()) == "fake_authority"


def test_a_renamed_guard_fails_rather_than_substring_matching() -> None:
    """The bug this file exists for: "fake_authority" is a substring of
    "DISABLED_fake_authority", so substring matching passed a broken guard."""
    checks = score(
        Expect(findings=["fake_authority"]),
        [observation(findings=["notice:DISABLED_fake_authority: x"])],
    )
    assert checks["findings"].passed is False


def test_an_exact_kind_passes() -> None:
    checks = score(
        Expect(findings=["fake_authority"]),
        [observation(findings=["notice:fake_authority: x"])],
    )
    assert checks["findings"].passed is True


def test_an_unexpected_extra_finding_fails() -> None:
    """Expectations are exact: a new guard firing on a clean ticket is a
    regression, not a bonus."""
    checks = score(
        Expect(findings=[]),
        [observation(findings=["notice:override_instructions: x"])],
    )
    assert checks["findings"].passed is False


def test_majority_decides_a_flaky_result() -> None:
    checks = score(
        Expect(category="billing"),
        [
            observation(category="billing"),
            observation(category="billing"),
            observation(category="general"),
        ],
    )
    assert checks["category"].passed is True
    assert checks["category"].actual == ["billing", "billing", "general"]


def test_a_minority_result_fails() -> None:
    checks = score(
        Expect(category="billing"),
        [
            observation(category="billing"),
            observation(category="general"),
            observation(category="general"),
        ],
    )
    assert checks["category"].passed is False


def test_unset_expectations_are_not_checked() -> None:
    checks = score(Expect(), [observation(category="anything")])
    assert "category" not in checks


def test_the_golden_set_loads_and_is_uniquely_named() -> None:
    scenarios = load_scenarios(SCENARIOS)
    assert len(scenarios) >= 9
    assert len({s.name for s in scenarios}) == len(scenarios)


def test_duplicate_scenario_names_are_rejected(tmp_path: Path) -> None:
    """Results are keyed by name, so a duplicate would silently overwrite."""
    (tmp_path / "a.yaml").write_text(
        "- name: dupe\n  title: t\n  description: d\n  expect: {}\n"
        "- name: dupe\n  title: t\n  description: d\n  expect: {}\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_scenarios(tmp_path)


class TestFlakyDetection:
    """A result that passed on majority but not every trial is unsettled, and
    saying so is the difference between a suite and a coin flip."""

    def test_unanimous_trials_are_not_flaky(self) -> None:
        checks = score(
            Expect(category="billing"),
            [observation(category="billing"), observation(category="billing")],
        )

        assert checks["category"].unanimous is True

    def test_disagreeing_trials_are_flaky_even_when_they_pass(self) -> None:
        checks = score(
            Expect(category="billing"),
            [
                observation(category="billing"),
                observation(category="billing"),
                observation(category="general"),
            ],
        )

        assert checks["category"].passed is True, "majority still carries it"
        assert checks["category"].unanimous is False, "but it is not settled"

    def test_a_single_trial_can_never_look_flaky(self) -> None:
        """Which is exactly why trials=1 is for iterating, not for deciding."""
        checks = score(Expect(category="billing"), [observation(category="billing")])

        assert checks["category"].unanimous is True


class TestAnEvalRunIsOneTrace:
    """An eval that traces as loose nodes is the flat list of model calls this
    project exists to complain about, looked at from the inside."""

    async def test_the_run_has_a_single_root(self) -> None:
        from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
        from assistant.tracing import trace_store
        from evals.core.runner import run_trial
        from evals.core.scenario import Scenario

        scripted = AgentConfig(
            models=dict.fromkeys(
                ModelPurpose, ModelConfig(provider="unconfigured", name="none")
            )
        )
        scenario = Scenario(
            name="t",
            title="Charged twice",
            description="Two charges on my card.",
            expect=Expect(),
        )

        await run_trial(scenario, scripted)

        run = trace_store.runs()[-1]
        roots = trace_store.tree(run)
        assert [root["name"] for root in roots] == ["support run"]
