"""What a customer is allowed to read.

Filtering in the client leaves an internal note one devtools tab away, so the
label has to be enforced where the data is served.
"""

from typing import Any

from rest_framework.test import APIClient

import pytest

from helpdesk.accounts.factories import UserFactory
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import CommentEvent, Visibility


@pytest.fixture
def customer(db: Any) -> Any:
    return UserFactory.create(is_staff=False)


@pytest.fixture
def agent(db: Any) -> Any:
    return UserFactory.create(is_staff=True)


@pytest.fixture
def ticket(customer: Any) -> Any:
    ticket = TicketFactory.create(created_by=customer)
    CommentEvent.objects.create(
        ticket=ticket,
        content="I was charged twice.",
        created_by=customer,
        visibility=Visibility.PUBLIC,
    )
    CommentEvent.objects.create(
        ticket=ticket,
        content="Finance says it is our bug.",
        created_by=None,
        visibility=Visibility.INTERNAL,
    )
    return ticket


def events_for(user: Any, ticket: Any) -> list[dict[str, Any]]:
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(f"/api/tickets/{ticket.id}/events/")
    assert response.status_code == 200
    body = response.json()
    rows = body["results"] if isinstance(body, dict) else body
    return list(rows)


class TestEvents:
    def test_a_customer_is_not_sent_internal_notes(
        self, customer: Any, ticket: Any
    ) -> None:
        contents = [e["content"] for e in events_for(customer, ticket)]

        assert "I was charged twice." in contents
        assert "Finance says it is our bug." not in contents

    def test_staff_see_the_whole_thread(self, agent: Any, ticket: Any) -> None:
        contents = [e["content"] for e in events_for(agent, ticket)]

        assert "Finance says it is our bug." in contents


class TestTicketList:
    def test_a_customer_sees_only_their_own(
        self, customer: Any, agent: Any, ticket: Any
    ) -> None:
        TicketFactory.create(created_by=agent, title="Someone else's problem")

        client = APIClient()
        client.force_authenticate(customer)
        body = client.get("/api/tickets/").json()
        titles = [
            t["title"] for t in (body["results"] if isinstance(body, dict) else body)
        ]

        assert ticket.title in titles
        assert "Someone else's problem" not in titles

    def test_staff_see_the_queue(self, customer: Any, agent: Any, ticket: Any) -> None:
        TicketFactory.create(created_by=agent, title="Someone else's problem")

        client = APIClient()
        client.force_authenticate(agent)
        body = client.get("/api/tickets/").json()
        titles = [
            t["title"] for t in (body["results"] if isinstance(body, dict) else body)
        ]

        assert {ticket.title, "Someone else's problem"} <= set(titles)
