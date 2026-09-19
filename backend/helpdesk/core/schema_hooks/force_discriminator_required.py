"""Make polymorphic `oneOf` schemas into well-formed discriminated unions.

drf-spectacular emits each variant of a polymorphic serializer as
`allOf: [{event_type: string}, {$ref: CommentEvent}]`. That shape is awkward for
every client generator: the variant is an intersection rather than an object, and
the discriminator is an open `string` instead of the one literal that identifies
it. openapi-zod-client turns it into `z.intersection(...)`, which Zod's
`discriminatedUnion` rejects outright.

This hook flattens each variant into a single object and narrows its
discriminator to a one-value enum, which is what the OpenAPI discriminator
contract actually implies.
"""

from typing import Any


def force_discriminator_required_hook(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    schemas: dict[str, Any] = result.get("components", {}).get("schemas", {})

    for schema in list(schemas.values()):
        discriminator = schema.get("discriminator")
        if not discriminator or "oneOf" not in schema:
            continue

        property_name = discriminator.get("propertyName")
        mapping: dict[str, str] = discriminator.get("mapping", {})
        if not property_name or not mapping:
            continue

        # Camelize renames the variants' fields but leaves the discriminator
        # pointing at the old snake_case name.
        property_name = _camelize(property_name)
        discriminator["propertyName"] = property_name

        for literal, ref in mapping.items():
            variant_name = ref.rsplit("/", 1)[-1]
            variant = schemas.get(variant_name)
            if variant is not None:
                schemas[variant_name] = _flatten(
                    variant, schemas, property_name, literal
                )

    return result


def _flatten(
    variant: dict[str, Any],
    schemas: dict[str, Any],
    property_name: str,
    literal: str,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for part in variant.get("allOf", [variant]):
        resolved = _resolve(part, schemas)
        properties.update(resolved.get("properties", {}))
        for field in resolved.get("required", []):
            if field not in required:
                required.append(field)

    # drf-spectacular injects a synthetic `{<snake_name>: string}` member that
    # camelize leaves alone, so the merge can carry both spellings. Keep one.
    for key in [k for k in properties if k != property_name and _camelize(k) == property_name]:
        del properties[key]
        if key in required:
            required.remove(key)

    # The whole point of the discriminator: this variant is exactly this value.
    properties[property_name] = {"type": "string", "enum": [literal]}
    if property_name not in required:
        required.append(property_name)

    flattened = {"type": "object", "properties": properties, "required": required}
    if description := variant.get("description"):
        flattened["description"] = description
    return flattened


def _camelize(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _resolve(schema: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not ref:
        return schema
    return schemas.get(ref.rsplit("/", 1)[-1], {})
