from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class StaffWrites(BasePermission):
    """Read your own, open a new one, change nothing.

    Scoping the queryset is not enough: a customer owns their ticket and could
    otherwise close it, raise its priority, or delete it along with every event
    on it.
    """

    message = "Only staff can change a ticket."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, "action", None) == "create":
            return True
        user: Any = request.user
        return bool(user.is_staff)
