/**
 * A tool's JSON Schema, as a Zod schema.
 *
 * The REST schemas are already Zod, generated from OpenAPI. A tool's arguments
 * arrive over the WebSocket as JSON Schema, derived by the agent from the
 * function's own signature. Converting here means one form engine covers both,
 * and the reviewer's form validates against the same statement of the arguments
 * that the tool will be called with.
 *
 * Deliberately narrow: it handles what a tool signature produces - strings,
 * numbers, integers, booleans, enums, optionals - and falls back to a
 * permissive type for anything else, so an unfamiliar argument stays editable
 * instead of disappearing from the form.
 */

import { z } from 'zod';

interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: unknown;
}

interface JsonSchemaProperty {
  type?: string;
  description?: string;
  enum?: unknown[];
  anyOf?: JsonSchemaProperty[];
  minimum?: number;
  maximum?: number;
  default?: unknown;
}

/** Arguments a person answers in a sentence rather than a word. */
const FREE_TEXT = /reason|note|message|comment|body|detail|explanation/i;

export function isFreeText(name: string, description?: string): boolean {
  return FREE_TEXT.test(name) || FREE_TEXT.test(description ?? '');
}

function branchOf(property: JsonSchemaProperty): JsonSchemaProperty {
  // `str | None` arrives as anyOf; the null branch is what `required` covers.
  const real = property.anyOf?.find((branch) => branch.type !== 'null');
  return real ?? property;
}

function scalar(property: JsonSchemaProperty): z.ZodTypeAny {
  const resolved = branchOf(property);

  if (Array.isArray(resolved.enum) && resolved.enum.length > 0) {
    const values = resolved.enum.map(String) as [string, ...string[]];
    return z.enum(values);
  }

  switch (resolved.type) {
    case 'number':
    case 'integer': {
      let schema = z.number();
      if (resolved.type === 'integer') schema = schema.int();
      if (typeof resolved.minimum === 'number')
        schema = schema.min(resolved.minimum);
      if (typeof resolved.maximum === 'number')
        schema = schema.max(resolved.maximum);
      return schema;
    }
    case 'boolean':
      return z.boolean();
    case 'string':
      return z.string();
    default:
      // Unknown or missing type: editable as text rather than dropped. The
      // agent validates the call anyway, so guessing wrong costs a message,
      // not a field the reviewer cannot see.
      return z.string();
  }
}

export function zodFromJsonSchema(
  schema: Record<string, unknown> | undefined,
): z.ZodObject<z.ZodRawShape> {
  const { properties, required } = (schema ?? {}) as JsonSchema;
  const mandatory = new Set(
    Array.isArray(required) ? required.map(String) : [],
  );

  const shape: z.ZodRawShape = {};
  for (const [name, property] of Object.entries(properties ?? {})) {
    let field = scalar(property);

    const description = branchOf(property).description ?? property.description;
    if (description) field = field.describe(description);

    if (mandatory.has(name)) {
      // A required string must not be satisfiable by the empty string: the
      // tool would refuse the call, and the form should say so first.
      if (field instanceof z.ZodString) field = field.min(1, 'Required');
    } else {
      field = field.optional();
    }

    shape[name] = field;
  }

  return z.object(shape);
}
