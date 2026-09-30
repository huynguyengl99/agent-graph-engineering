import type { AutoFormFieldProps } from '../types';
import { FieldShell, inputClass } from './shared';

/** The fallback: anything with no more specific handler. */
export function AutoFormInput({
  name,
  value,
  onChange,
  onBlur,
  inputRef,
  label,
  description,
  required,
  error,
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
      <input
        id={name}
        name={name}
        ref={inputRef}
        aria-label={label}
        type="text"
        disabled={disabled}
        className={inputClass(error)}
        value={(value as string | undefined) ?? ''}
        onBlur={onBlur}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldShell>
  );
}
