/**
 * A form built by reading a Zod schema.
 *
 * One engine for two sources of schema, which is the point: the REST schemas
 * come from the OpenAPI generator, and a tool's arguments arrive over the
 * WebSocket as JSON Schema and are converted (see `lib/zodFromJsonSchema`).
 * Either way the form, its validation and its defaults are read off the same
 * object, so a form cannot promise something the server will reject.
 *
 * Hand-written forms are what rot: a field is added server-side, the form is
 * not updated, and nobody finds out until a request fails or - worse, for the
 * tool gate - until a reviewer approves a call whose arguments they were never
 * shown.
 */

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Controller,
  FormProvider,
  useForm,
  type Resolver,
} from 'react-hook-form';
import { z } from 'zod';

import { INPUT_COMPONENTS, ZOD_HANDLERS } from './config';
import type { ApiFieldError, FieldConfig, FieldConfigItem } from './types';
import {
  beautifyName,
  getBaseType,
  getDefaultValues,
  getDescription,
  getEnumValues,
  getObjectSchema,
  isRequired,
  type ZodObjectOrWrapped,
} from './utils';

export { AutoFormSubmit } from './submit';
export type { ApiFieldError, FieldConfig } from './types';

type Values = Record<string, unknown>;

interface Props<Schema extends ZodObjectOrWrapped> {
  schema: Schema;
  /** Starting values, e.g. what a model proposed or what a record holds. */
  values?: Values;
  onSubmit: (values: z.infer<Schema>) => void;
  /** Per-field overrides. Everything not named here is read off the schema. */
  fieldConfig?: FieldConfig<z.infer<Schema>>;
  /** Fields the caller sets itself, so they are neither shown nor asked for. */
  hiddenFields?: string[];
  apiErrors?: ApiFieldError[];
  disabled?: boolean;
  children?: React.ReactNode;
  className?: string;
  onValuesChange?: (values: Values) => void;
}

export function AutoForm<Schema extends ZodObjectOrWrapped>({
  schema,
  values,
  onSubmit,
  fieldConfig,
  hiddenFields = [],
  apiErrors = [],
  disabled = false,
  children,
  className,
  onValuesChange,
}: Props<Schema>) {
  const object = useMemo(() => getObjectSchema(schema), [schema]);

  const form = useForm<Values>({
    resolver: zodResolver(schema as never) as Resolver<Values>,
    defaultValues: { ...getDefaultValues(object), ...values },
    // onChange, so `isValid` is live: the submit button reads it to stay
    // disabled while the values would not satisfy the schema.
    mode: 'onChange',
  });

  const errors = form.formState.errors;
  const byField = new Map(apiErrors.map((e) => [e.field, e.error]));

  return (
    <FormProvider {...form}>
      <form
        className={className ?? 'space-y-3'}
        onSubmit={form.handleSubmit((submitted) =>
          onSubmit(submitted as z.infer<Schema>),
        )}
        onChange={() => onValuesChange?.(form.getValues())}
      >
        {Object.entries(object.shape).map(([name, field]) => {
          if (hiddenFields.includes(name)) return null;

          const config: FieldConfigItem =
            (fieldConfig as Record<string, FieldConfigItem> | undefined)?.[
              name
            ] ?? {};
          const kind =
            config.fieldType ?? ZOD_HANDLERS[getBaseType(field)] ?? 'fallback';
          const Component = INPUT_COMPONENTS[kind];

          return (
            // Controller, not register: the field components are controlled, and
            // `register` hands back no value, so a number or a checkbox would
            // render blank however full the form actually is.
            <Controller
              key={name}
              name={name}
              control={form.control}
              render={({ field: controlled }) => (
                <Component
                  name={controlled.name}
                  value={controlled.value}
                  onChange={controlled.onChange}
                  onBlur={controlled.onBlur}
                  inputRef={controlled.ref as never}
                  schema={field}
                  label={config.label ?? beautifyName(name)}
                  description={config.description ?? getDescription(field)}
                  required={isRequired(field)}
                  options={getEnumValues(field)}
                  disabled={disabled}
                  error={
                    (errors[name]?.message as string | undefined) ??
                    byField.get(name)
                  }
                />
              )}
            />
          );
        })}

        {children}
      </form>
    </FormProvider>
  );
}
