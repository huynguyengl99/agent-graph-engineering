import type { ReactNode } from 'react';

/** The label, help text and error every field shares. */
export function FieldShell({
  label,
  description,
  required,
  error,
  children,
  htmlFor,
}: {
  label: string;
  description?: string;
  required: boolean;
  error?: string;
  children: ReactNode;
  htmlFor: string;
}) {
  return (
    <div className="block">
      <label
        htmlFor={htmlFor}
        className="flex items-center gap-2 text-xs font-medium text-gray-700"
      >
        {label}
        {required && <span className="text-gray-500">required</span>}
      </label>
      {description && (
        <p className="mt-0.5 text-xs text-gray-500">{description}</p>
      )}
      <div className="mt-1">{children}</div>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export const inputClass = (error?: string) =>
  `w-full rounded border px-3 py-2 text-sm ${
    error ? 'border-red-400' : 'border-gray-300'
  }`;
