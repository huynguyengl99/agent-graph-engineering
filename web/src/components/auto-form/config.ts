import type { ComponentType } from 'react';
import { AutoFormCheckbox } from './fields/checkbox';
import { AutoFormInput } from './fields/input';
import { AutoFormNumber } from './fields/number';
import { AutoFormSelect } from './fields/select';
import { AutoFormTextarea } from './fields/textarea';
import type { AutoFormFieldProps } from './types';

export const INPUT_COMPONENTS = {
  checkbox: AutoFormCheckbox,
  number: AutoFormNumber,
  select: AutoFormSelect,
  textarea: AutoFormTextarea,
  fallback: AutoFormInput,
} satisfies Record<string, ComponentType<AutoFormFieldProps>>;

export type INPUT_COMPONENT = keyof typeof INPUT_COMPONENTS;

/**
 * Which component handles which Zod type.
 *
 * Adding a type means one line here, not a branch in every form. Anything
 * unlisted falls back to a text input, so an unfamiliar type is still editable
 * rather than invisible.
 */
export const ZOD_HANDLERS: Record<string, INPUT_COMPONENT> = {
  ZodBoolean: 'checkbox',
  ZodNumber: 'number',
  ZodBigInt: 'number',
  ZodEnum: 'select',
  ZodNativeEnum: 'select',
};
