/**
 * Keeping the access cookie fresh.
 *
 * The cookies are HttpOnly, so expiry is tracked from what login and refresh
 * return rather than read back. Refreshing happens on the way out rather than
 * after a 401: reacting would have every in-flight request fail once first.
 */

import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';

/** Refresh this long before expiry, to cover clock skew and the trip itself. */
const EARLY_SECONDS = 30;
const STORED_AT = 'auth-session';

/** Endpoints that must not wait on a refresh, or would recurse into one. */
const UNAUTHENTICATED = [
  '/accounts/login/',
  '/accounts/registration/',
  '/accounts/token/refresh/',
];

export type Expiry = {
  accessExpiration?: string;
  refreshExpiration?: string;
};

type Refresher = () => Promise<Expiry>;

let expiry: Expiry = read();
let refresher: Refresher | null = null;
let inFlight: Promise<void> | null = null;

function read(): Expiry {
  try {
    return JSON.parse(localStorage.getItem(STORED_AT) ?? '{}') as Expiry;
  } catch {
    return {};
  }
}

function write(next: Expiry): void {
  try {
    localStorage.setItem(STORED_AT, JSON.stringify(next));
  } catch {
    // A private window can refuse; the session still works until it expires.
  }
}

/** Survives a reload, so the first request after one does not have to fail. */
export function rememberSession(next: Expiry): void {
  expiry = {
    accessExpiration: next.accessExpiration ?? expiry.accessExpiration,
    refreshExpiration: next.refreshExpiration ?? expiry.refreshExpiration,
  };
  write(expiry);
}

export function forgetSession(): void {
  expiry = {};
  write(expiry);
}

export function refreshSessionWith(next: Refresher): void {
  refresher = next;
}

const valid = (at: string | undefined): boolean =>
  !!at && new Date(at).getTime() > Date.now() + EARLY_SECONDS * 1000;

/** One refresh at a time, so a burst of requests makes one call, not six. */
function refresh(): Promise<void> {
  inFlight ??= (refresher?.() ?? Promise.resolve({}))
    .then(rememberSession)
    .catch(forgetSession)
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export async function ensureFreshSession(url = ''): Promise<void> {
  if (UNAUTHENTICATED.some((path) => url.includes(path))) return;
  if (valid(expiry.accessExpiration)) return;
  if (!valid(expiry.refreshExpiration)) return;
  await refresh();
}

export function keepSessionFresh(instance: AxiosInstance): void {
  instance.interceptors.request.use(
    async (config: InternalAxiosRequestConfig) => {
      await ensureFreshSession(config.url ?? '');
      return config;
    },
  );
}
