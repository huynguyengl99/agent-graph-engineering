"""Which tools a scenario actually asserts.

    uv run python -m evals.coverage

A tool nobody has written a scenario for is one whose behaviour is a guess, and
the gap is invisible from a passing suite: every scenario can pass while the
riskiest tool has never been chosen by a model.
"""

from pathlib import Path

import assistant.tools  # noqa: F401  # registers the tools
from assistant.tools.core import metadata_for, selectable_tools

from evals.core.scenario import load_scenarios

SCENARIOS = Path(__file__).parent / "scenarios"


def asserted() -> set[str]:
    return {s.expect.tool for s in load_scenarios(SCENARIOS) if s.expect.tool}


def main() -> int:
    # Only the ones a planner may choose: a tool the graph calls
    # itself is never picked by a model, so no scenario can assert it.
    registered = set(selectable_tools())
    covered = asserted() & registered
    uncovered = sorted(registered - covered)

    print(f"{len(covered)}/{len(registered)} tools are named by a scenario\n")
    for tool in sorted(covered):
        print(f"  covered    {tool}")
    for tool in uncovered:
        gate = " (irreversible)" if metadata_for(tool).requires_approval else ""
        print(f"  NO SCENARIO {tool}{gate}")

    if uncovered:
        print(
            "\nA tool with no scenario is not untested - the suites and the "
            "smoke may still reach it - but nothing measures whether a model "
            "picks it when it should."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
