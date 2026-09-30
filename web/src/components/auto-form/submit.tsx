import { useFormState } from 'react-hook-form';

/**
 * Submit, disabled while the schema is not satisfied.
 *
 * Reads form state from context rather than taking props, so a caller can put
 * it anywhere among the form's children without threading validity through.
 * Disabling is the honest affordance: the server would refuse these values,
 * and at the tool gate the tool would refuse the call, so refusing here says so
 * before anyone clicks.
 */
export function AutoFormSubmit({
  children,
  disabled = false,
  className,
}: {
  children?: React.ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const { isValid, isSubmitting } = useFormState();

  return (
    <button
      type="submit"
      disabled={disabled || isSubmitting || !isValid}
      className={
        className ??
        'rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40'
      }
    >
      {children ?? 'Submit'}
    </button>
  );
}
