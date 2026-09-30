import type { AutoFormFieldProps } from '../types';

export function AutoFormCheckbox({
  name,
  value,
  onChange,
  onBlur,
  inputRef,
  label,
  description,
  error,
  disabled,
}: AutoFormFieldProps) {
  return (
    <div>
      <label htmlFor={name} className="flex items-center gap-2 text-sm">
        <input
          id={name}
          name={name}
          ref={inputRef}
          aria-label={label}
          type="checkbox"
          disabled={disabled}
          checked={Boolean(value)}
          onBlur={onBlur}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="font-medium text-gray-700">{label}</span>
      </label>
      {description && (
        <p className="mt-0.5 text-xs text-gray-500">{description}</p>
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
