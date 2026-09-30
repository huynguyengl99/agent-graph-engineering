import type { AutoFormFieldProps } from '../types';
import { FieldShell, inputClass } from './shared';

/** A Zod enum knows its own options, so nothing here lists them by hand. */
export function AutoFormSelect({
  name,
  value,
  onChange,
  onBlur,
  inputRef,
  label,
  description,
  required,
  error,
  options,
  disabled,
}: AutoFormFieldProps) {
  return (
    <FieldShell
      htmlFor={name}
      label={label}
      description={description}
      required={required}
      error={error}
    >
      <select
        id={name}
        name={name}
        ref={inputRef}
        aria-label={label}
        disabled={disabled}
        className={inputClass(error)}
        value={(value as string | undefined) ?? ''}
        onBlur={onBlur}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        {!required && <option value="">-</option>}
        {(options ?? []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}
