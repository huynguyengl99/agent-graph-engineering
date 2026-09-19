/**
 * API clients.
 *
 * Both go through Vite's dev proxy, so the base URL is relative and session
 * cookies ride along on same-origin requests.
 */

import axios from 'axios';
import { createApiClient } from '@/schemas/backend';

// Auth endpoints are not part of the generated ticket surface.
export const apiClient = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Generated from the backend's OpenAPI document. Paths, parameters, and
 * responses are validated by Zod at runtime, so a backend change the frontend
 * has not regenerated for fails loudly instead of silently.
 */
export const api = createApiClient('', {
  axiosConfig: { withCredentials: true },
});
