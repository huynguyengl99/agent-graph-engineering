/**
 * The other half of the backend's contract: `{{a short name}}` is a value the
 * agent could not fill, and nothing carrying one may be sent to the customer.
 * Square brackets are citations, so they are not it.
 */

const PLACEHOLDER = /\{\{\s*([^{}]{1,60}?)\s*\}\}/g;

export function placeholdersIn(text: string): string[] {
  return [...new Set([...(text ?? '').matchAll(PLACEHOLDER)].map((m) => m[1]))];
}

export function fillPlaceholders(
  text: string,
  values: Record<string, string>,
): string {
  return (text ?? '').replace(PLACEHOLDER, (whole, name: string) =>
    values[name]?.trim() ? values[name] : whole,
  );
}
