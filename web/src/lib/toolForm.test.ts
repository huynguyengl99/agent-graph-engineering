import { describe, expect, it } from 'vitest';
import { zodFromJsonSchema } from './zodFromJsonSchema';
import { corrections, decisionArguments } from './toolForm';

const SCHEMA = zodFromJsonSchema({
  type: 'object',
  required: ['email', 'amount'],
  properties: {
    email: { type: 'string' },
    amount: { type: 'number' },
    reason: { type: 'string' },
  },
});

const PROPOSED = { email: 'demo@example.com', amount: 29, reason: 'Duplicate' };

describe('corrections', () => {
  it('reports only what the reviewer changed', () => {
    expect(corrections(SCHEMA, { ...PROPOSED, amount: 9 }, PROPOSED)).toEqual({
      amount: 9,
    });
  });

  it('is empty when the form comes back as it went out', () => {
    expect(corrections(SCHEMA, PROPOSED, PROPOSED)).toEqual({});
  });

  it('counts filling in an argument the planner left out', () => {
    const proposed = { amount: 29, reason: 'Duplicate' };

    expect(
      corrections(SCHEMA, { ...proposed, email: 'demo@example.com' }, proposed),
    ).toEqual({ email: 'demo@example.com' });
  });

  it('does not count an untouched empty field as a change', () => {
    const proposed = { email: 'demo@example.com', amount: 29 };

    expect(
      corrections(SCHEMA, { ...proposed, reason: undefined }, proposed),
    ).toEqual({});
  });

  it('ignores anything outside the schema', () => {
    // A planner that misnames an argument has it dropped by the agent; this is
    // the second line of defence, at the point the wire payload is built.
    const proposed = { ...PROPOSED, customer_email: 'demo@example.com' };

    expect(corrections(SCHEMA, { ...proposed, amount: 9 }, proposed)).toEqual({
      amount: 9,
    });
  });
});

describe('decisionArguments', () => {
  it('sends nothing when nothing changed, so approval stays approval', () => {
    expect(decisionArguments(SCHEMA, PROPOSED, PROPOSED)).toEqual({});
  });

  it('sends the whole argument set once anything changed', () => {
    // The gate replaces the arguments wholesale, so a patch would drop the
    // fields the reviewer left alone - the email, here.
    expect(
      decisionArguments(SCHEMA, { ...PROPOSED, amount: 9 }, PROPOSED),
    ).toEqual({
      email: 'demo@example.com',
      amount: 9,
      reason: 'Duplicate',
    });
  });

  it('never sends an argument the tool does not accept', () => {
    const proposed = { ...PROPOSED, customer_email: 'demo@example.com' };

    expect(
      decisionArguments(SCHEMA, { ...proposed, amount: 9 }, proposed),
    ).not.toHaveProperty('customer_email');
  });
});
