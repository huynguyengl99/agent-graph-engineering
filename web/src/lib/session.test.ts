import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ensureFreshSession,
  forgetSession,
  refreshSessionWith,
  rememberSession,
} from './session';

const inSeconds = (n: number) => new Date(Date.now() + n * 1000).toISOString();

describe('session refresh', () => {
  beforeEach(() => {
    localStorage.clear();
    forgetSession();
  });

  it('does not refresh while the access cookie is good', async () => {
    const refresh = vi.fn().mockResolvedValue({});
    refreshSessionWith(refresh);
    rememberSession({
      accessExpiration: inSeconds(300),
      refreshExpiration: inSeconds(86400),
    });

    await ensureFreshSession('/api/tickets/');

    expect(refresh).not.toHaveBeenCalled();
  });

  it('refreshes before expiry rather than after, to cover the trip', async () => {
    const refresh = vi
      .fn()
      .mockResolvedValue({ accessExpiration: inSeconds(300) });
    refreshSessionWith(refresh);
    rememberSession({
      accessExpiration: inSeconds(5),
      refreshExpiration: inSeconds(86400),
    });

    await ensureFreshSession('/api/tickets/');

    expect(refresh).toHaveBeenCalledOnce();
  });

  it('makes one call for a burst, not one per request', async () => {
    let release: (v: unknown) => void = () => {};
    const refresh = vi
      .fn()
      .mockReturnValue(new Promise((r) => (release = r)).then(() => ({})));
    refreshSessionWith(refresh);
    rememberSession({
      accessExpiration: inSeconds(-1),
      refreshExpiration: inSeconds(86400),
    });

    const all = Promise.all([
      ensureFreshSession('/api/tickets/'),
      ensureFreshSession('/api/conversations/'),
      ensureFreshSession('/api/accounts/user/'),
    ]);
    release(null);
    await all;

    expect(refresh).toHaveBeenCalledOnce();
  });

  it('never refreshes the refresh endpoint itself', async () => {
    const refresh = vi.fn().mockResolvedValue({});
    refreshSessionWith(refresh);
    rememberSession({
      accessExpiration: inSeconds(-1),
      refreshExpiration: inSeconds(86400),
    });

    await ensureFreshSession('/api/accounts/token/refresh/');

    expect(refresh).not.toHaveBeenCalled();
  });

  it('gives up once the refresh cookie is past it', async () => {
    const refresh = vi.fn().mockResolvedValue({});
    refreshSessionWith(refresh);
    rememberSession({
      accessExpiration: inSeconds(-100),
      refreshExpiration: inSeconds(-1),
    });

    await ensureFreshSession('/api/tickets/');

    expect(refresh).not.toHaveBeenCalled();
  });

  it('survives a reload, so the first request after one is not a 401', async () => {
    rememberSession({
      accessExpiration: inSeconds(300),
      refreshExpiration: inSeconds(86400),
    });

    expect(
      JSON.parse(localStorage.getItem('auth-session') ?? '{}'),
    ).toMatchObject({
      accessExpiration: expect.any(String),
      refreshExpiration: expect.any(String),
    });
  });

  it('forgets everything on logout', async () => {
    rememberSession({ accessExpiration: inSeconds(300) });
    forgetSession();

    expect(localStorage.getItem('auth-session')).toBe('{}');
  });
});
