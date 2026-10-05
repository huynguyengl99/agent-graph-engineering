"""Run results on disk: one directory per run, plus a `latest` pointer."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from evals.core.judge import Verdict
from evals.core.scoring import Check

RESULTS_DIR = Path(__file__).parent.parent / "results"


class Usage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # False when any model in the run has no price table, e.g. the scripted one.
    priced: bool = True
    unpriced_models: list[str] = []


class ScenarioResult(BaseModel):
    scenario: str
    trials: int
    pass_rate: float
    # True when the trials disagreed: it passed on majority, but not every
    # time. Invisible at trials=1, which is why that is not the default to
    # trust a decision on.
    flaky: bool = False
    # Not run: it needs a provider and there is no key. Neither passed nor failed.
    skipped: bool = False
    deterministic: dict[str, Check] = {}
    judged: Verdict | None = None
    passed: bool
    usage: Usage
    error: str | None = None


class RunSummary(BaseModel):
    run_id: str
    git_commit: str
    models: dict[str, str]
    trials: int
    total: int
    passed: int
    failed: int
    flaky: int = 0
    skipped: int = 0
    usage: Usage
    results: list[ScenarioResult]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def write(summary: RunSummary, label: str, *, whole_set: bool = True) -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d/%H-%M-%S")
    run_dir = RESULTS_DIR / "runs" / f"{stamp}_{label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = summary.model_dump_json(indent=2)
    (run_dir / "summary.json").write_text(payload)

    # A stable path to diff against, so `compare` needs no run id. Only a whole
    # run belongs there: chasing one scenario would otherwise leave `latest`
    # holding that scenario alone, and `compare` diffing it against twenty.
    if whole_set:
        latest = RESULTS_DIR / "latest"
        latest.mkdir(parents=True, exist_ok=True)
        (latest / f"{label}.json").write_text(payload)

    return run_dir
