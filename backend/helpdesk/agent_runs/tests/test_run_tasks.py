"""That a request queues instead of running, and survives the trip."""

from typing import Any
from unittest.mock import AsyncMock, patch

from django.test import TestCase

from helpdesk.agent_runs import tasks
from helpdesk.tickets.models import Visibility
from helpdesk.tickets.services import support


class TestRequestsAreQueued(TestCase):
    """The web process must not be the thing that runs the agent."""

    async def test_starting_a_run_queues_it(self) -> None:
        with patch.object(tasks.run_ticket, "delay") as delay:
            await support.start_run(
                "t-1", question="why?", visibility=Visibility.PUBLIC, user_id=7
            )
        delay.assert_called_once_with(
            "t-1", question="why?", visibility=Visibility.PUBLIC, user_id=7
        )

    async def test_approving_queues_the_resume(self) -> None:
        with patch.object(tasks.resume_approval, "delay") as delay:
            await support.start_approval(
                "t-1", approved=True, content="edited", user_id=7
            )
        delay.assert_called_once_with("t-1", approved=True, content="edited", user_id=7)

    async def test_a_tool_decision_carries_the_reviewers_arguments(self) -> None:
        """The corrected value is what runs, so it has to survive the queue."""
        with patch.object(tasks.resume_tool_decision, "delay") as delay:
            await support.start_tool_decision(
                "t-1", approved=True, arguments={"amount": "9.00"}, publish=True
            )
        delay.assert_called_once_with(
            "t-1", approved=True, arguments={"amount": "9.00"}, publish=True
        )


class TestTasksCallTheService(TestCase):
    """Each task awaits the function that already did the work."""

    def test_run_ticket(self) -> None:
        with patch("helpdesk.tickets.services.support.run", new=AsyncMock()) as run:
            tasks.run_ticket("t-1", question="why?", visibility="public")
        run.assert_awaited_once_with(
            "t-1", question="why?", visibility="public", user_id=None
        )

    def test_resume_tool_decision(self) -> None:
        with patch(
            "helpdesk.tickets.services.support.decide_tool", new=AsyncMock()
        ) as decide:
            tasks.resume_tool_decision(
                "t-1", approved=False, arguments={}, publish=False
            )
        decide.assert_awaited_once_with(
            "t-1", approved=False, arguments={}, publish=False
        )


class TestCrashSafety(TestCase):
    """None is a Celery default, and losing one breaks nothing until a kill."""

    def test_the_task_is_acked_after_it_finishes(self) -> None:
        from django.conf import settings

        assert settings.CELERY_TASK_ACKS_LATE is True
        assert settings.CELERY_TASK_REJECT_ON_WORKER_LOST is True

    def test_redelivery_outlasts_the_longest_run(self) -> None:
        """Expire mid-run and a second worker gets it too."""
        from django.conf import settings

        visibility: Any = settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"]
        assert visibility > settings.CELERY_TASK_TIME_LIMIT

    def test_redelivery_waits_for_the_lane_to_go_stale(self) -> None:
        """Redeliver too early and the retry no-ops on the stale lane, then acks."""
        from django.conf import settings

        visibility: Any = settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"]
        assert visibility > settings.AGENT_RUN_CLAIM_TIMEOUT
