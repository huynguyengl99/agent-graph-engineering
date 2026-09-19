"""OpenAPI schema view without error schemas.

This view strips error-related schemas from the OpenAPI output to produce
cleaner schemas for frontend code generation. Error handling is typically
done at the API client level, so error schemas in generated types are noise.
"""
from http import HTTPStatus
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.views import SpectacularAPIView


class SpectacularNoErrorAPIView(SpectacularAPIView):
    """
    OpenAPI schema view that excludes error-related schemas.

    This view is designed for frontend code generation tools. It removes:
    - Error response schemas
    - Validation error schemas
    - HTTP error status codes from endpoint responses

    The result is a cleaner schema focused on successful API interactions.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return OpenAPI schema without error schemas."""
        response = super().get(request, *args, **kwargs)

        if response.status_code == HTTPStatus.OK and isinstance(response.data, dict):
            schema = response.data
            self._strip_error_schemas(schema)

        return response

    def _strip_error_schemas(self, schema: dict[str, Any]) -> None:
        """
        Remove error-related schemas from OpenAPI spec.

        Modifies the schema in-place to remove:
        1. Error and ValidationError component schemas
        2. Non-2xx response definitions from paths
        """
        # Remove error schemas from components
        components = schema.get("components", {})
        schemas = components.get("schemas", {})

        error_schema_names = [
            name
            for name in schemas.keys()
            if "Error" in name or "error" in name.lower()
        ]

        for name in error_schema_names:
            schemas.pop(name, None)

        # Remove non-2xx responses from paths
        paths = schema.get("paths", {})
        for path_item in paths.values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue

                responses = operation.get("responses", {})
                success_responses = {
                    code: resp for code, resp in responses.items() if code.startswith("2")
                }
                operation["responses"] = success_responses
