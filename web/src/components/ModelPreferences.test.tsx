// @vitest-environment happy-dom
/**
 * The form is generated from the same schema the API publishes, so these tests
 * never name a field that the server does not declare.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ModelPreferences } from './ModelPreferences';

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(async () => ({
      results: [{ purpose: 'answer', model: 'openai:gpt-4o' }],
    })),
    post: vi.fn(async () => ({ purpose: 'decision', model: 'anthropic:x' })),
  },
}));

afterEach(cleanup);

describe('ModelPreferences', () => {
  it('renders a select for purpose, because the server declared it an enum', async () => {
    render(<ModelPreferences />);

    const purpose = (await screen.findByLabelText(
      'Purpose',
    )) as HTMLSelectElement;
    expect(purpose.tagName).toBe('SELECT');
    expect(Array.from(purpose.options).map((o) => o.value)).toEqual([
      'decision',
      'answer',
    ]);
  });

  it('lists what is already set', async () => {
    render(<ModelPreferences />);

    // Scoped to the list: "answer" is also one of the select's options.
    const row = await screen.findByRole('listitem');
    expect(row.textContent).toContain('answer');
    expect(row.textContent).toContain('openai:gpt-4o');
  });

  it('asks for the model as provider:name', () => {
    render(<ModelPreferences />);

    expect(screen.getByLabelText('Model')).toBeTruthy();
    expect(screen.getByText(/provider:name/)).toBeTruthy();
  });
});
