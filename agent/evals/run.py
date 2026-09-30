"""Run the golden set.

    uv run python -m evals.run                      # every scenario
    uv run python -m evals.run routing              # names matching "routing"
    uv run python -m evals.run --config claude      # a different model set
    uv run python -m evals.run --trials 3           # settle a flaky result

Configs are `evals/configs/<name>.json`; the run is labelled by the model that
actually answered, so two providers land in separate result files and
`evals.compare` can diff them.

Runs without an API key: the scripted model makes the deterministic checks
meaningful and the judge falls back to its free checks, so the harness itself
is always exercised even when the answers are canned.
"""

import asyncio
import sys
from pathlib import Path

from evals.core.config import EvalConfig
from evals.core.judge import CascadeJudge
from evals.core.results import (
    RunSummary,
    ScenarioResult,
    Usage,
    git_commit,
    write,
)
from evals.core.runner import Observation, run_trial
from evals.core.scenario import Scenario, load_scenarios
from evals.core.scoring import score

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def _usage(observations: list[Observation]) -> Usage:
    total = Usage()
    for o in observations:
        total = Usage(
            calls=total.calls + o.cost.calls,
            input_tokens=total.input_tokens + o.cost.input_tokens,
            output_tokens=total.output_tokens + o.cost.output_tokens,
            cost_usd=total.cost_usd + float(o.cost.cost_usd),
            priced=total.priced and o.cost.priced,
            unpriced_models=sorted(
                set(total.unpriced_models) | o.cost.unpriced_models
            ),
        )
    return total


async def run_scenario(
    scenario: Scenario, config: EvalConfig, judge: CascadeJudge
) -> ScenarioResult:
    observations = [
        await run_trial(scenario, config.agent_config) for _ in range(config.trials)
    ]

    errors = [o.error for o in observations if o.error]
    checks = score(scenario.expect, observations)
    deterministic_passed = all(c.passed for c in checks.values())

    verdict = None
    if scenario.expect.answer is not None and not errors:
        # Judge the first trial: a judged criterion is prose, and scoring the
        # same prose three times mostly buys judge variance.
        verdict = await judge.judge(
            observations[0].answer,
            scenario.expect.answer,
            observations[0].kb_snippets,
        )

    passed = bool(
        not errors and deterministic_passed and (verdict is None or verdict.passed)
    )
    flaky = passed and any(not check.unanimous for check in checks.values())
    return ScenarioResult(
        scenario=scenario.name,
        trials=config.trials,
        pass_rate=1.0 if passed else 0.0,
        flaky=flaky,
        deterministic=checks,
        judged=verdict,
        passed=passed,
        usage=_usage(observations),
        error=errors[0] if errors else None,
    )


async def main(
    pattern: str | None = None,
    config_name: str | None = None,
    trials: int | None = None,
) -> int:
    config = EvalConfig.load(config_name)
    if trials is not None:
        config = config.model_copy(update={"trials": trials})
    scenarios = load_scenarios(SCENARIOS_DIR)
    if pattern:
        scenarios = [s for s in scenarios if pattern in s.name]
    if not scenarios:
        print("no scenarios matched")
        return 1

    judge = CascadeJudge(config.judge)
    results = [await run_scenario(s, config, judge) for s in scenarios]

    total_usage = Usage()
    for r in results:
        total_usage = Usage(
            calls=total_usage.calls + r.usage.calls,
            input_tokens=total_usage.input_tokens + r.usage.input_tokens,
            output_tokens=total_usage.output_tokens + r.usage.output_tokens,
            cost_usd=total_usage.cost_usd + r.usage.cost_usd,
            priced=total_usage.priced and r.usage.priced,
            unpriced_models=sorted(
                set(total_usage.unpriced_models) | set(r.usage.unpriced_models)
            ),
        )

    summary = RunSummary(
        run_id=git_commit(),
        git_commit=git_commit(),
        models={k: config.resolved(k) for k in config.models},
        trials=config.trials,
        total=len(results),
        passed=sum(r.passed for r in results),
        failed=sum(not r.passed for r in results),
        flaky=sum(r.flaky for r in results),
        usage=total_usage,
        results=results,
    )

    run_dir = write(summary, config.label)
    _report(summary, run_dir)
    return 0 if summary.failed == 0 else 1


def _report(summary: RunSummary, run_dir: Path) -> None:
    for r in summary.results:
        mark = "FLAKY" if r.flaky else ("PASS" if r.passed else "FAIL")
        print(f"  {mark:5} {r.scenario}")
        if not r.passed:
            for name, check in r.deterministic.items():
                if not check.passed:
                    print(f"          {name}: expected {check.expected!r}, got {check.actual!r}")
            if r.judged and not r.judged.passed:
                print(f"          answer: {r.judged.reasoning}")
            if r.error:
                print(f"          error: {r.error}")

    cost = (
        f"${summary.usage.cost_usd:.4f}"
        if summary.usage.priced
        else f"unpriced (no price table for {', '.join(summary.usage.unpriced_models)})"
    )
    print(
        f"\n{summary.passed}/{summary.total} passed  "
        f"({summary.usage.calls} model calls, "
        f"{summary.usage.input_tokens + summary.usage.output_tokens} tokens, {cost})"
    )

    if summary.flaky:
        print(
            f"{summary.flaky} scenario(s) passed on majority but not every "
            "trial - treat those as unsettled."
        )
    elif summary.trials == 1:
        print("trials=1, so a single bad sample fails a scenario. --trials 3 to settle one.")

    skipped = [r.scenario for r in summary.results if r.judged and not r.judged.judged]
    if skipped:
        print(
            f"{len(skipped)} scenario(s) had their prose criteria skipped: "
            "set a provider key to judge them."
        )
    print(f"written to {run_dir}")


def _parse(argv: list[str]) -> tuple[str | None, str | None, int | None]:
    rest = list(argv)

    def take(flag: str) -> str | None:
        if flag not in rest:
            return None
        index = rest.index(flag)
        value = rest[index + 1] if index + 1 < len(rest) else None
        del rest[index : index + 2]
        return value

    config = take("--config")
    trials = take("--trials")
    pattern = rest[0] if rest else None
    return pattern, config, int(trials) if trials else None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(*_parse(sys.argv[1:]))))
