import { describe, expect, it } from 'vitest';

/**
 * Importing this module used to throw "Zodios: missing base url" at load,
 * which blanked the whole app: nothing else imports it in a test, so the
 * failure only showed up in a browser.
 */
describe('api client', () => {
  it('constructs with a usable base url', async () => {
    const { api } = await import('./api');
    expect(api.baseURL).toBe(window.location.origin);
  });
});
