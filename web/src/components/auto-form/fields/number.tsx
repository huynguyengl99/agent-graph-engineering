import type { AutoFormFieldProps } from '../types';
import { FieldShell, inputClass } from './shared';

export function AutoFormNumber({
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
        type="number"
        step="any"
        disabled={disabled}
        className={inputClass(error)}
        value={(value as number | string | undefined) ?? ''}
        onBlur={onBlur}
        onChange={(e) =>
          // Empty stays undefined rather than becoming 0: a required field the
          // reviewer cleared has to fail validation, not quietly mean zero.
          onChange(e.target.value === '' ? undefined : e.target.valueAsNumber)
        }
      />
    </FieldShell>
  );
}
