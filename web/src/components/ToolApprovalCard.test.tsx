// @vitest-environment happy-dom
/**
 * The card is generated from the schema, so these tests never name a tool's
 * fields in markup - they put them in the schema and expect inputs to appear.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToolApprovalCard } from './ToolApprovalCard';

const PROPOSAL = {
  tool: 'issue_refund',
  description: 'Refund a charge.',
  arguments: { email: 'demo@example.com', amount: 29, reason: 'Duplicate' },
  argumentsSchema: {
    type: 'object',
    required: ['email', 'amount', 'reason'],
    properties: {
      email: { type: 'string', description: 'Who to refund.' },
      amount: { type: 'number', description: 'In pounds.' },
      reason: { type: 'string', description: 'Why.' },
    },
  },
};

const input = (label: string) =>
  screen.getByLabelText(label) as HTMLInputElement;
const button = (name: RegExp) =>
  screen.getByRole('button', { name }) as HTMLButtonElement;

afterEach(cleanup);

describe('ToolApprovalCard', () => {
  it('renders an input per schema property, filled with the proposal', () => {
    render(<ToolApprovalCard proposal={PROPOSAL} onDecide={vi.fn()} />);

    expect(input('Email').value).toBe('demo@example.com');
    expect(input('Amount').value).toBe('29');
    // `reason` reads as prose, so it gets room for a sentence.
    expect(screen.getByLabelText('Reason').tagName).toBe('TEXTAREA');
  });

  it('approves as proposed without sending arguments', () => {
    const onDecide = vi.fn();
    render(<ToolApprovalCard proposal={PROPOSAL} onDecide={onDecide} />);

    fireEvent.click(button(/approve and run/i));

    expect(onDecide).toHaveBeenCalledWith(true, {});
  });

  it('sends the full corrected argument set once a field changes', () => {
    const onDecide = vi.fn();
    render(<ToolApprovalCard proposal={PROPOSAL} onDecide={onDecide} />);

    fireEvent.change(input('Amount'), { target: { value: '9' } });
    fireEvent.click(button(/run with my corrections/i));

    expect(onDecide).toHaveBeenCalledWith(true, {
      email: 'demo@example.com',
      amount: 9,
      reason: 'Duplicate',
    });
  });

  it('cancels without arguments', () => {
    const onDecide = vi.fn();
    render(<ToolApprovalCard proposal={PROPOSAL} onDecide={onDecide} />);

    fireEvent.click(button(/cancel/i));

    expect(onDecide).toHaveBeenCalledWith(false, {});
  });

  it('explains an argument the planner made up, rather than showing a blank field', () => {
    render(
      <ToolApprovalCard
        proposal={{
          ...PROPOSAL,
          arguments: { amount: 29, reason: 'Duplicate' },
          unknownArguments: ['customer_email'],
        }}
        onDecide={vi.fn()}
      />,
    );

    expect(screen.getByText(/customer_email/)).toBeTruthy();
  });

  it('will not approve while a required field is empty', () => {
    const onDecide = vi.fn();
    render(
      <ToolApprovalCard
        proposal={{
          ...PROPOSAL,
          arguments: { amount: 29, reason: 'Duplicate' },
        }}
        onDecide={onDecide}
      />,
    );

    expect(button(/approve and run/i).disabled).toBe(true);
    fireEvent.click(button(/approve and run/i));
    expect(onDecide).not.toHaveBeenCalled();

    // Filling it in is all it takes: the reviewer repairs what the model got
    // wrong instead of being sent back to the assistant.
    fireEvent.change(input('Email'), { target: { value: 'demo@example.com' } });
    expect(button(/run with my corrections/i).disabled).toBe(false);
  });

  it('says so rather than breaking when a tool takes no arguments', () => {
    render(
      <ToolApprovalCard
        proposal={{ tool: 'ping', description: '', arguments: {} }}
        onDecide={vi.fn()}
      />,
    );

    expect(screen.getByText(/takes no arguments/i)).toBeTruthy();
  });
});
