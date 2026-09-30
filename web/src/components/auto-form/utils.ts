/**
 * Zod introspection: everything the form needs, read off the schema.
 *
 * A Zod schema already states the field names, their types, which are optional,
 * their defaults and their validation. A form built by reading it cannot
 * disagree with what the server will accept, because there is only one
 * statement of it.
 */

import { z } from 'zod';

export type ZodObjectOrWrapped =
  z.ZodObject<z.ZodRawShape> | z.ZodEffects<never>;

/** `amount_in_pence` and `amountInPence` both read as a label. */
export function beautifyName(name: string): string {
  const spaced = name
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** The innermost type, past optional, nullable, default and refinement wrappers. */
function getBaseSchema(schema: z.ZodTypeAny): z.ZodTypeAny {
  const def = schema._def as {
    innerType?: z.ZodTypeAny;
    schema?: z.ZodTypeAny;
  };
  if (def.innerType) return getBaseSchema(def.innerType);
  if (def.schema) return getBaseSchema(def.schema);
  return schema;
}

/** `ZodString`, `ZodNumber`, ... - what the handler table is keyed on. */
export function getBaseType(schema: z.ZodTypeAny): string {
  return (getBaseSchema(schema)._def as { typeName: string }).typeName;
}

/** A `.default()` anywhere in the stack. */
function getDefaultInZodStack(schema: z.ZodTypeAny): unknown {
  const def = schema._def as {
    typeName?: string;
    defaultValue?: () => unknown;
    innerType?: z.ZodTypeAny;
    schema?: z.ZodTypeAny;
  };
  if (def.typeName === 'ZodDefault') return def.defaultValue?.();
  if (def.innerType) return getDefaultInZodStack(def.innerType);
  if (def.schema) return getDefaultInZodStack(def.schema);
  return undefined;
}

export function getDefaultValues(
  schema: z.ZodObject<z.ZodRawShape>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [name, field] of Object.entries(schema.shape)) {
    const value = getDefaultInZodStack(field);
    if (value !== undefined) values[name] = value;
  }
  return values;
}

/** Optional in the schema is optional on the form. Nothing else decides it. */
export function isRequired(schema: z.ZodTypeAny): boolean {
  return !schema.isOptional() && !schema.isNullable();
}

export function getEnumValues(schema: z.ZodTypeAny): string[] | undefined {
  const base = getBaseSchema(schema);
  const def = base._def as { typeName: string; values?: unknown };
  if (def.typeName !== 'ZodEnum') return undefined;
  const values = def.values;
  return Array.isArray(values) ? values.map(String) : undefined;
}

/** The description a Zod `.describe()` carries, used as field help. */
export function getDescription(schema: z.ZodTypeAny): string | undefined {
  return schema.description ?? getBaseSchema(schema).description;
}

/** Unwrap a schema wrapped in `.refine()`/`.superRefine()` to its object. */
export function getObjectSchema(
  schema: ZodObjectOrWrapped,
): z.ZodObject<z.ZodRawShape> {
  const base = getBaseSchema(schema as z.ZodTypeAny);
  if (getBaseType(base) === 'ZodObject') {
    return base as z.ZodObject<z.ZodRawShape>;
  }
  throw new Error('AutoForm needs an object schema');
}
