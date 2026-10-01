import type { ApiFieldError } from '@/components/auto-form';

interface StandardizedError {
  type?: string;
  errors?: { attr?: string; detail?: string }[];
}

/**
 * Field errors from a failed request, for `AutoForm`'s `apiErrors`.
 *
 * The backend uses drf-standardized-errors, so the body is
 * `{"errors": [{"attr": "model", "detail": "..."}]}` rather than DRF's plain
 * `{"model": ["..."]}`. Parsing the plain shape found nothing and showed the
 * reviewer a generic failure while the server had said exactly what was wrong.
 * The plain shape is still handled, for any view that bypasses the handler.
 */
export function fieldErrors(data: unknown): ApiFieldError[] {
  if (!data || typeof data !== 'object') return [];

  const standardized = (data as StandardizedError).errors;
  if (Array.isArray(standardized)) {
    return standardized
      .filter((e) => e.attr && e.detail)
      .map((e) => ({ field: String(e.attr), error: String(e.detail) }));
  }

  return Object.entries(data as Record<string, unknown>)
    .filter(([, value]) => Array.isArray(value) || typeof value === 'string')
    .map(([field, value]) => ({
      field,
      error: String(Array.isArray(value) ? value[0] : value),
    }));
}

/** The body of a failed Zodios/axios call, wherever it ended up. */
export function errorBody(error: unknown): unknown {
  return (error as { response?: { data?: unknown } }).response?.data;
}
