import { describe, expect, it } from 'vitest';
import {
  corrections,
  decisionArguments,
  fieldsFromSchema,
  initialValues,
} from './toolForm';

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
} satisfies Record<string, unknown>;

const PROPOSED = {
  email: 'demo@example.com',
  amount: 29.0,
  reason: 'Duplicate',
};

describe('fieldsFromSchema', () => {
  it('keeps the schema order, so the form reads like the signature', () => {
    expect(fieldsFromSchema(REFUND).map((f) => f.name)).toEqual([
      'email',
      'amount',
      'reason',
      'notify',
      'channel',
      'attempts',
      'note',
    ]);
  });

  it('maps each JSON Schema type to an input that can produce it', () => {
    const byName = Object.fromEntries(
      fieldsFromSchema(REFUND).map((f) => [f.name, f.kind]),
    );

    expect(byName).toMatchObject({
      email: 'string',
      amount: 'number',
      notify: 'boolean',
      channel: 'enum',
      attempts: 'integer',
    });
  });

  it('gives a free-text argument room to be answered properly', () => {
    expect(
      fieldsFromSchema(REFUND).find((f) => f.name === 'reason')?.kind,
    ).toBe('text');
  });

  it('looks through an optional type to what it actually is', () => {
    // `str | None` is anyOf[string, null]; rendering that as an unknown type
    // would leave the field uneditable.
    expect(fieldsFromSchema(REFUND).find((f) => f.name === 'note')?.kind).toBe(
      'text',
    );
  });

  it('carries the docstring description through as the field help', () => {
    expect(fieldsFromSchema(REFUND)[0].description).toBe('Who to refund.');
  });

  it('marks what the tool cannot run without', () => {
    const required = fieldsFromSchema(REFUND)
      .filter((f) => f.required)
      .map((f) => f.name);
    expect(required).toEqual(['email', 'amount']);
  });

  it('is empty rather than broken when a tool takes no arguments', () => {
    expect(fieldsFromSchema(undefined)).toEqual([]);
    expect(fieldsFromSchema({ type: 'object' })).toEqual([]);
  });

  it('labels a field without inventing copy for it', () => {
    const fields = fieldsFromSchema({
      properties: { amount_in_pence: { type: 'integer' } },
    });
    expect(fields[0].label).toBe('Amount in pence');
  });
});

describe('initialValues', () => {
  it('starts every field at what the assistant proposed', () => {
    const values = initialValues(fieldsFromSchema(REFUND), PROPOSED);

    expect(values.email).toBe('demo@example.com');
    expect(values.amount).toBe('29');
    // A field the assistant left out is empty, not "undefined".
    expect(values.channel).toBe('');
  });
});

describe('corrections', () => {
  const fields = fieldsFromSchema(REFUND);

  it('reports only what the reviewer changed', () => {
    const values = { ...initialValues(fields, PROPOSED), amount: '9' };

    expect(corrections(fields, values, PROPOSED)).toEqual({ amount: 9 });
  });

  it('does not treat retyping the same number as an edit', () => {
    // The proposal is 29.0; the input shows 29. Counting that as a correction
    // would badge every approval as edited.
    const values = { ...initialValues(fields, PROPOSED), amount: '29.0' };

    expect(corrections(fields, values, PROPOSED)).toEqual({});
  });

  it('parses a number back to a number, not a string', () => {
    const values = { ...initialValues(fields, PROPOSED), amount: '9.5' };

    expect(corrections(fields, values, PROPOSED).amount).toBe(9.5);
  });

  it('parses a boolean choice back to a boolean', () => {
    const values = { ...initialValues(fields, PROPOSED), notify: 'true' };

    expect(corrections(fields, values, PROPOSED).notify).toBe(true);
  });

  it('leaves an unparseable number as typed for the agent to reject', () => {
    const values = { ...initialValues(fields, PROPOSED), amount: 'twenty' };

    expect(corrections(fields, values, PROPOSED).amount).toBe('twenty');
  });
});

describe('decisionArguments', () => {
  const fields = fieldsFromSchema(REFUND);

  it('sends nothing when nothing changed, so approval stays approval', () => {
    expect(
      decisionArguments(fields, initialValues(fields, PROPOSED), PROPOSED),
    ).toEqual({});
  });

  it('never sends an argument the tool does not accept', () => {
    // A planner that misnames an argument used to have it merged straight back
    // in, where it crashed the call - and the reviewer never saw the field, so
    // they had not approved it.
    const proposed = { ...PROPOSED, customer_email: 'demo@example.com' };
    const values = { ...initialValues(fields, proposed), amount: '9' };

    expect(decisionArguments(fields, values, proposed)).not.toHaveProperty(
      'customer_email',
    );
  });

  it('sends the whole argument set once anything changed', () => {
    // The gate replaces the arguments wholesale, so a patch would drop the
    // fields the reviewer left alone - the email, here.
    const values = { ...initialValues(fields, PROPOSED), amount: '9' };

    expect(decisionArguments(fields, values, PROPOSED)).toEqual({
      email: 'demo@example.com',
      amount: 9,
      reason: 'Duplicate',
    });
  });
});
