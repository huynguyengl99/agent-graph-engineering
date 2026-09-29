import factory

from helpdesk.accounts.factories import UserFactory
from helpdesk.conversations.models import Conversation
from helpdesk.test_utils import BaseModelFactory


class ConversationFactory(BaseModelFactory[Conversation]):
    title = factory.Faker("sentence", nb_words=4)
    owner = factory.SubFactory(UserFactory)
    ticket = None
