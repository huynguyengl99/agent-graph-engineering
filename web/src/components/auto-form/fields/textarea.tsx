import type { AutoFormFieldProps } from '../types';
import { FieldShell, inputClass } from './shared';

/** For arguments answered in a sentence: a one-line input invites five words. */
export function AutoFormTextarea({
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
      <textarea
        id={name}
        name={name}
        ref={inputRef}
        aria-label={label}
        rows={3}
        disabled={disabled}
        className={inputClass(error)}
        value={(value as string | undefined) ?? ''}
        onBlur={onBlur}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldShell>
  );
}
