// @vitest-environment happy-dom
/**
 * What the agent writes is markdown, and before this it reached the screen as
 * literal asterisks. The streaming case is the one a plain renderer gets
 * wrong: half a reply often has an emphasis opened and not yet closed.
 * Streamdown renders bold as a marked span rather than `<strong>`.
 */
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Markdown } from './Markdown';

afterEach(cleanup);

describe('Markdown', () => {
  it('renders emphasis rather than showing the asterisks', () => {
    const { container } = render(
      <Markdown>{'**Customer-facing reply:** we are on it'}</Markdown>,
    );
    expect(
      container.querySelector('[data-streamdown="strong"]')?.textContent,
    ).toBe('Customer-facing reply:');
    expect(container.textContent).not.toContain('**');
  });

  it('keeps a single newline as a line break', () => {
    const { container } = render(<Markdown>{'**Draft:**\nThanks'}</Markdown>);
    expect(container.querySelector('br')).not.toBeNull();
  });

  it('closes an emphasis that has not finished arriving', () => {
    const { container } = render(
      <Markdown streaming>{'**Customer-facing hold'}</Markdown>,
    );
    expect(
      container.querySelector('[data-streamdown="strong"]')?.textContent,
    ).toBe('Customer-facing hold');
    expect(container.textContent).not.toContain('**');
  });

  it('does not run markup the model wrote', () => {
    const { container } = render(
      <Markdown>
        {'<script>alert(1)</script><img src=x onerror="alert(1)">'}
      </Markdown>,
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
  });
});
