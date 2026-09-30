/**
 * Build a review form out of a tool's JSON Schema.
 *
 * The agent derives the schema from the tool's own signature and docstring, so
 * nothing in the browser knows what `issue_refund` is. Adding a tool to the
 * agent makes it reviewable here on the next proposal, with no change to this
 * file - which is the point. A hand-written form per tool is the thing that
 * silently rots: the tool grows an argument, the form does not, and a reviewer
 * approves a call whose arguments they were never shown.
 *
 * Only *changed* fields are submitted back. Re-sending every field would turn
 * the reviewer's normalisation - a trimmed string, a number retyped - into an
 * edit the agent is told about, and the "corrected" badge would be on every
 * approval.
 */

export type FieldKind =
  'string' | 'text' | 'number' | 'integer' | 'boolean' | 'enum';

export interface ToolField {
  name: string;
  label: string;
  kind: FieldKind;
  description?: string;
  required: boolean;
  options?: string[];
}

interface JsonSchema {
  properties?: Record<string, Record<string, unknown>>;
  required?: unknown;
}

/** `amount_in_pence` reads as a field label, not as a key. */
function humanize(name: string): string {
  const words = name.replace(/[_-]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Arguments a person answers in a sentence rather than a word. */
const FREE_TEXT = /reason|note|message|comment|body|detail|explanation/i;

function kindOf(name: string, property: Record<string, unknown>): FieldKind {
  const options = property.enum;
  if (Array.isArray(options)) return 'enum';

  // `str | None` arrives as anyOf; the null branch is what `required` covers.
  const branches = property.anyOf;
  if (Array.isArray(branches)) {
    const real = branches.find(
      (branch): branch is Record<string, unknown> =>
        typeof branch === 'object' &&
        branch !== null &&
        (branch as Record<string, unknown>).type !== 'null',
    );
    if (real) return kindOf(name, real);
  }

  switch (property.type) {
    case 'number':
      return 'number';
    case 'integer':
      return 'integer';
    case 'boolean':
      return 'boolean';
    default:
      // A long free-text argument is a reason to give, and a one-line input
      // invites a five-word one. The name is the stronger signal: a `note`
      // argument is free text whether or not its docstring says so.
      return FREE_TEXT.test(name) ||
        FREE_TEXT.test(String(property.description ?? ''))
        ? 'text'
        : 'string';
  }
}

function optionsOf(property: Record<string, unknown>): string[] | undefined {
  const options = property.enum;
  return Array.isArray(options) ? options.map(String) : undefined;
}

export function fieldsFromSchema(
  schema: Record<string, unknown> | undefined,
): ToolField[] {
  const { properties, required } = (schema ?? {}) as JsonSchema;
  if (!properties) return [];

  const mandatory = new Set(
    Array.isArray(required) ? required.map(String) : [],
  );

  return Object.entries(properties).map(([name, property]) => ({
    name,
    label: humanize(name),
    kind: kindOf(name, property),
    description:
      typeof property.description === 'string'
        ? property.description
        : undefined,
    required: mandatory.has(name),
    options: optionsOf(property),
  }));
}

/** What a field starts as: the proposed value, rendered for an input. */
export function initialValues(
  fields: ToolField[],
  proposed: Record<string, unknown> | undefined,
): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of fields) {
    const value = proposed?.[field.name];
    values[field.name] =
      value === undefined || value === null ? '' : String(value);
  }
  return values;
}

function parse(field: ToolField, raw: string): unknown {
  switch (field.kind) {
    case 'number':
    case 'integer': {
      const value = Number(raw);
      // An unparseable number is left as typed rather than sent as NaN, so the
      // agent's own validation reports it instead of the tool crashing.
      return Number.isNaN(value) ? raw : value;
    }
    case 'boolean':
      return raw === 'true';
    default:
      return raw;
  }
}

/**
 * The fields the reviewer actually changed, parsed back to their real types.
 *
 * Comparison is on the rendered form of the proposal, so retyping `29.0` as
 * `29` is not a correction.
 */
export function corrections(
  fields: ToolField[],
  values: Record<string, string>,
  proposed: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const original = initialValues(fields, proposed);
  const changed: Record<string, unknown> = {};

  for (const field of fields) {
    const value = values[field.name] ?? '';
    if (value === original[field.name]) continue;
    if (parse(field, value) === parse(field, original[field.name] ?? ''))
      continue;
    changed[field.name] = parse(field, value);
  }
  return changed;
}

/**
 * What goes on the wire: a correction is the whole argument set, not a patch.
 *
 * The gate replaces the proposed arguments wholesale, so a partial object
 * would drop the fields the reviewer left alone. Sending nothing when nothing
 * changed is what keeps "approved as proposed" distinguishable.
 */
export function decisionArguments(
  fields: ToolField[],
  values: Record<string, string>,
  proposed: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const changed = corrections(fields, values, proposed);
  if (Object.keys(changed).length === 0) return {};

  // Built from the fields, not from the proposal: a key the tool does not
  // accept would crash the call, and it is not on the form, so the reviewer
  // never saw it and cannot be said to have approved it.
  const args: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.name in changed) {
      args[field.name] = changed[field.name];
    } else if (proposed && field.name in proposed) {
      args[field.name] = proposed[field.name];
    }
  }
  return args;
}

/** Required fields the reviewer has left empty. */
export function incomplete(
  fields: ToolField[],
  values: Record<string, string>,
): string[] {
  return fields
    .filter(
      (field) => field.required && (values[field.name] ?? '').trim() === '',
    )
    .map((field) => field.label);
}
