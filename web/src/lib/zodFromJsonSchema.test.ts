/**
 * The bridge that lets one form engine serve both transports: REST schemas
 * arrive as Zod from the OpenAPI generator, and a tool's arguments arrive as
 * JSON Schema over the WebSocket.
 */
import { describe, expect, it } from 'vitest';
import {
  getBaseType,
  getEnumValues,
  isRequired,
} from '@/components/auto-form/utils';
import { isFreeText, zodFromJsonSchema } from './zodFromJsonSchema';

const REFUND = {
  type: 'object',
  required: ['email', 'amount'],
  properties: {
    email: { type: 'string', description: 'Who to refund.' },
    amount: { type: 'number', description: 'Amount in pounds.' },
    reason: { type: 'string', description: 'Reason shown on the statement.' },
    notify: { type: 'boolean' },
    channel: { enum: ['email', 'sms'] },
    attempts: { type: 'integer' },
    note: { anyOf: [{ type: 'string' }, { type: 'null' }] },
  },
};

const shapeOf = (schema: Record<string, unknown>) =>
  zodFromJsonSchema(schema).shape;

describe('zodFromJsonSchema', () => {
  it('keeps the schema order, so the form reads like the signature', () => {
    expect(Object.keys(shapeOf(REFUND))).toEqual([
      'email',
      'amount',
      'reason',
      'notify',
      'channel',
      'attempts',
      'note',
    ]);
  });

  it('maps each JSON Schema type to the Zod type the form dispatches on', () => {
    const shape = shapeOf(REFUND);

    expect(getBaseType(shape.email)).toBe('ZodString');
    expect(getBaseType(shape.amount)).toBe('ZodNumber');
    expect(getBaseType(shape.notify)).toBe('ZodBoolean');
    expect(getBaseType(shape.channel)).toBe('ZodEnum');
    expect(getBaseType(shape.attempts)).toBe('ZodNumber');
  });

  it('carries an enum’s own options, so no form lists them by hand', () => {
    expect(getEnumValues(shapeOf(REFUND).channel)).toEqual(['email', 'sms']);
  });

  it('looks through an optional type to what it actually is', () => {
    // `str | None` is anyOf[string, null]. Rendering that as an unknown type
    // would leave the field uneditable.
    expect(getBaseType(shapeOf(REFUND).note)).toBe('ZodString');
  });

  it('makes required and optional match the schema, not a convention', () => {
    const shape = shapeOf(REFUND);

    expect(isRequired(shape.email)).toBe(true);
    expect(isRequired(shape.amount)).toBe(true);
    expect(isRequired(shape.reason)).toBe(false);
  });

  it('carries the docstring description through as field help', () => {
    expect(shapeOf(REFUND).email.description).toBe('Who to refund.');
  });

  it('will not accept an empty string for a required field', () => {
    // The tool would refuse the call; the form has to refuse first, or a
    // reviewer approves a call with a hole in it.
    const schema = zodFromJsonSchema(REFUND);

    expect(schema.safeParse({ email: '', amount: 9 }).success).toBe(false);
    expect(schema.safeParse({ email: 'a@b.c', amount: 9 }).success).toBe(true);
  });

  it('rejects a number the reviewer typed as words', () => {
    const schema = zodFromJsonSchema(REFUND);

    expect(schema.safeParse({ email: 'a@b.c', amount: 'twenty' }).success).toBe(
      false,
    );
  });

  it('keeps an integer argument whole', () => {
    const result = zodFromJsonSchema(REFUND).safeParse({
      email: 'a@b.c',
      amount: 9,
      attempts: 1.5,
    });

    expect(result.success).toBe(false);
  });

  it('carries a numeric bound through, so the form refuses before the tool does', () => {
    const schema = zodFromJsonSchema({
      required: ['amount'],
      properties: { amount: { type: 'number', minimum: 1, maximum: 500 } },
    });

    expect(schema.safeParse({ amount: 0 }).success).toBe(false);
    expect(schema.safeParse({ amount: 501 }).success).toBe(false);
    expect(schema.safeParse({ amount: 500 }).success).toBe(true);
  });

  it('is an empty object rather than broken when a tool takes no arguments', () => {
    expect(Object.keys(zodFromJsonSchema(undefined).shape)).toEqual([]);
    expect(Object.keys(zodFromJsonSchema({ type: 'object' }).shape)).toEqual(
      [],
    );
  });

  it('keeps an unfamiliar type editable instead of dropping the field', () => {
    const shape = shapeOf({ properties: { payload: { type: 'object' } } });

    // Not required, so it is wrapped in optional; the point is the inner type.
    expect(getBaseType(shape.payload)).toBe('ZodString');
  });
});

describe('isFreeText', () => {
  it('spots an argument answered in a sentence, by name or by description', () => {
    expect(isFreeText('reason')).toBe(true);
    expect(isFreeText('note')).toBe(true);
    // The name is the stronger signal, but a description counts too.
    expect(isFreeText('summary', 'A short message to show.')).toBe(true);
    expect(isFreeText('email', 'Who to refund.')).toBe(false);
  });
});
