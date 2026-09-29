"""Diff two runs, which is the question evals actually answer.

    uv run python -m evals.compare scripted openai_gpt-4o

Reads evals/results/latest/<label>.json, so it needs no run ids.
"""

import json
import sys

from evals.core.results import RESULTS_DIR, RunSummary


def load(label: str) -> RunSummary:
    path = RESULTS_DIR / "latest" / f"{label}.json"
    if not path.exists():
        raise SystemExit(f"no run for {label!r}; expected {path}")
    return RunSummary(**json.loads(path.read_text()))


def main(before_label: str, after_label: str) -> int:
    before, after = load(before_label), load(after_label)
    by_name = {r.scenario: r for r in before.results}

    regressions: list[str] = []
    for result in after.results:
        was = by_name.get(result.scenario)
        if was is None:
            print(f"  NEW    {result.scenario}: {'pass' if result.passed else 'FAIL'}")
        elif was.passed and not result.passed:
            regressions.append(result.scenario)
            print(f"  BROKE  {result.scenario}")
        elif not was.passed and result.passed:
            print(f"  FIXED  {result.scenario}")

    gone = sorted(set(by_name) - {r.scenario for r in after.results})
    for name in gone:
        print(f"  GONE   {name}")

    print(
        f"\n{before_label}: {before.passed}/{before.total}"
        f"   ->   {after_label}: {after.passed}/{after.total}"
    )
    if before.usage.priced and after.usage.priced:
        delta = after.usage.cost_usd - before.usage.cost_usd
        print(
            f"cost: ${before.usage.cost_usd:.4f} -> ${after.usage.cost_usd:.4f} "
            f"({delta:+.4f})"
        )
    else:
        print("cost: not comparable, one run used an unpriced model")

    return 1 if regressions else 0


if __name__ == "__main__":
    _, *args = sys.argv
    if len(args) != 2:  # noqa: PLR2004 - two labels, before and after
        raise SystemExit(__doc__)
    raise SystemExit(main(*args))
