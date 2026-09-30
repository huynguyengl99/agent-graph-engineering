import type { Ref } from 'react';
import type { z } from 'zod';
import type { INPUT_COMPONENT } from './config';

/**
 * What every field component gets.
 *
 * The pieces, not react-hook-form's `field` bag: a field component should not
 * need to know which form library drives it, and reading a name off an object
 * that also carries a ref is exactly what the React lint rules object to.
 */
export interface AutoFormFieldProps {
  name: string;
  value: unknown;
  onChange: (value: unknown) => void;
  onBlur: () => void;
  inputRef: Ref<never>;

  label: string;
  description?: string;
  required: boolean;
  options?: string[];
  error?: string;
  disabled?: boolean;
  schema: z.ZodTypeAny;
}

export interface FieldConfigItem {
  /** Override the component the Zod type would have chosen. */
  fieldType?: INPUT_COMPONENT;
  label?: string;
  description?: string;
}

export type FieldConfig<Values> = {
  [Key in keyof Values]?: FieldConfigItem;
};

/** A server-side field error, so `{"email": ["..."]}` lands on the email field. */
export interface ApiFieldError {
  field: string;
  error: string;
}
