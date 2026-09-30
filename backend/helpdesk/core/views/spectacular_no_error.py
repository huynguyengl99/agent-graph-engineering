"""The schema the frontend generator consumes.

Error responses are handled once in the API client, so their schemas are noise
in the generated types. This view serves the same schema with them removed.
"""

from http import HTTPStatus
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView


class SpectacularNoErrorAPIView(SpectacularAPIView):
    # Overriding `get` drops the parent's schema annotation, which makes
    # spectacular try (and fail) to guess a serializer for this view.
    @extend_schema(exclude=True)
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().get(request, *args, **kwargs)

        if response.status_code == HTTPStatus.OK and isinstance(response.data, dict):
            self._strip_error_schemas(response.data)

        return response  # type: ignore[no-any-return]

    def _strip_error_schemas(self, schema: dict[str, Any]) -> None:
        schemas: dict[str, Any] = schema.get("components", {}).get("schemas", {})
        for name in [n for n in schemas if "error" in n.lower()]:
            schemas.pop(name, None)

        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses", {})
                operation["responses"] = {
                    code: resp
                    for code, resp in responses.items()
                    if code.startswith("2")
                }
