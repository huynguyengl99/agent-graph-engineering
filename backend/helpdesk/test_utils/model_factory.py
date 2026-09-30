"""Base model factory with type hints support."""

from typing import Any, TypeVar, get_args

import factory
from asgiref.sync import sync_to_async
from factory.base import FactoryMetaClass

T = TypeVar("T")


class BaseFactoryMeta(FactoryMetaClass):
    """Metaclass that automatically sets model from type hints."""

    def __new__(
        mcs, class_name: str, bases: tuple[type, ...], attrs: dict[str, Any]
    ) -> type["BaseModelFactory[T]"]:  # pyright: ignore[reportInvalidTypeVarUse]
        orig_bases = attrs.get("__orig_bases__", [])
        for t in orig_bases:
            if t.__name__ == "BaseModelFactory" and t.__module__ == __name__:
                type_args = get_args(t)
                if len(type_args) == 1:
                    type_arg = type_args[0]
                    # Skip TypeVars - only set model for concrete classes
                    if isinstance(type_arg, TypeVar):
                        continue
                    if "Meta" not in attrs:
                        attrs["Meta"] = type("Meta", (), {})
                    attrs["Meta"].model = type_arg  # pyright: ignore
        return super().__new__(mcs, class_name, bases, attrs)  # type: ignore


class BaseModelFactory(factory.django.DjangoModelFactory[T], metaclass=BaseFactoryMeta):
    """
    Base factory for Django models with type hints support.

    Usage:
        class UserFactory(BaseModelFactory[User]):
            email = factory.Faker("email")
            # Meta.model is automatically set to User from type hint

    Features:
        - Automatic model detection from type hints
        - Async create support (acreate)
        - Type-safe create/build methods
    """

    class Meta:  # pyright: ignore
        abstract = True

    @classmethod
    def create(cls, **kwargs: Any) -> T:
        return super().create(**kwargs)

    @classmethod
    def build(cls, **kwargs: Any) -> T:
        return super().build(**kwargs)

    @classmethod
    async def acreate(cls, **kwargs: Any) -> T:
        return await sync_to_async(cls.create)(**kwargs)
