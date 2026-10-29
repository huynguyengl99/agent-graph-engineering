"""Prove the broker redelivers a task whose worker was killed.

`agent_runs/tests/test_redelivery.py` covers everything that happens *after* a
redelivery, and `test_run_tasks.py` asserts the settings are ordered right.
Neither can prove the redelivery itself: that is Redis and kombu behaviour,
and it only shows up when a worker actually dies.

So this kills one. It starts a worker, gives it a task, sends it `SIGKILL`
mid-task, starts a second worker, and waits to see the same task arrive again.
Nothing else is involved - no Django, no agent, no model - just the broker and
the three settings that decide whether a kill loses a run:

    task_acks_late              acknowledge at the end, not on delivery
    task_reject_on_worker_lost  and mean it for a hard kill too
    visibility_timeout          how long Redis waits before handing it on

Run it with `just crash-test`. It takes about a minute, mostly waiting, and
it needs only the Redis from `just infra-up`.

The visibility timeout here is seconds; in the app it is an hour, because it
has to outlast both the longest run and the lane claim. Shrinking it is the
only way to watch the mechanism work without waiting one.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from celery import Celery

BROKER = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
VISIBILITY_TIMEOUT = 10
# Long enough that the kill lands mid-task, short enough that the second
# worker finishes while somebody is still watching.
WORK_SECONDS = 25
QUEUE = "crash_test"
# Once for the worker that is killed, once for the one that recovers it.
EXPECTED_ATTEMPTS = 2
# How long to wait for the hand-over before calling the run lost.
PATIENCE = 300
ATTEMPTS = "crash_test:attempts"
DONE = "crash_test:done"

app = Celery("crash_test", broker=BROKER)
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue=QUEUE,
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT},
    broker_connection_retry_on_startup=True,
)


def store():
    import redis

    return redis.Redis.from_url(BROKER)


@app.task(name="crash_test.slow_work")
def slow_work() -> None:
    """Counts the times it was started, and the times it was allowed to end."""
    store().incr(ATTEMPTS)
    time.sleep(WORK_SECONDS)
    store().incr(DONE)


def worker(name: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            "--hostname",
            f"{name}@%h",
        ],
        # Its own group, so the kill reaches the worker and not this script.
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def count(key: str) -> int:
    return int(store().get(key) or 0)


def wait_for(key: str, n: int, *, seconds: int) -> float | None:
    """Seconds waited, or None if it never happened."""
    started = time.monotonic()
    deadline = started + seconds
    while time.monotonic() < deadline:
        if count(key) >= n:
            return time.monotonic() - started
        time.sleep(0.5)
    return None


def main() -> int:
    redis_store = store()
    redis_store.delete(ATTEMPTS, DONE)
    # A message left behind by an interrupted earlier run would be picked up
    # the moment a worker starts and counted as this run's redelivery.
    redis_store.delete(QUEUE, "unacked", "unacked_index")

    failures = 0

    def ok(label: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        print(("  PASS  " if condition else "  FAIL  ") + label, detail)
        failures += 0 if condition else 1

    print(f"== a killed worker's task comes back (visibility {VISIBILITY_TIMEOUT}s) ==")

    first = worker("killed")
    slow_work.delay()
    try:
        if wait_for(ATTEMPTS, 1, seconds=60) is None:
            print("  FAIL  the first worker never started it")
            return 1
        print("   started once, killing the worker mid-task")
        os.killpg(os.getpgid(first.pid), signal.SIGKILL)
        first.wait(timeout=30)
        ok("the worker is gone before it could finish", count(DONE) == 0)
    finally:
        if first.poll() is None:  # pragma: no cover - only on an early failure
            os.killpg(os.getpgid(first.pid), signal.SIGKILL)

    second = worker("recovered")
    try:
        # Generous, and measured rather than assumed. `visibility_timeout` is
        # when the message becomes eligible, not when it is handed over: kombu
        # restores timed-out messages on its own cycle, so the wait observed
        # here runs to several times the timeout. Sizing the real one against
        # the longest run leaves room for that; sizing it against the stopwatch
        # would not.
        redelivered = wait_for(ATTEMPTS, 2, seconds=PATIENCE)
        ok(
            "the task is handed to another worker",
            redelivered is not None,
            f"after {redelivered:.0f}s" if redelivered else "never, so it is lost",
        )
        ok(
            "and this time it is allowed to finish",
            wait_for(DONE, 1, seconds=WORK_SECONDS + 60) is not None,
        )
        ok(
            "it ran twice, not more",
            count(ATTEMPTS) == EXPECTED_ATTEMPTS,
            f"{count(ATTEMPTS)} attempts",
        )
    finally:
        second.terminate()
        try:
            second.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover
            os.killpg(os.getpgid(second.pid), signal.SIGKILL)
        redis_store.delete(ATTEMPTS, DONE)

    print()
    print("all good" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        app.worker_main(
            [
                "worker",
                "--pool=threads",
                "--concurrency=1",
                "-Q",
                QUEUE,
                "-l",
                "warning",
                *sys.argv[2:],
            ]
        )
    else:
        raise SystemExit(main())
