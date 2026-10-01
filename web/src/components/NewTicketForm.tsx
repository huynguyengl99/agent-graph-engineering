import { useState } from 'react';
import {
  AutoForm,
  AutoFormSubmit,
  type ApiFieldError,
} from '@/components/auto-form';
import { schemas } from '@/schemas/backend';
import { api } from '@/lib/api';
import { errorBody, fieldErrors } from '@/lib/apiErrors';
import type { Ticket } from '@/lib/types';

/**
 * Create a ticket from the generated request schema.
 *
 * The same `AutoForm` renders the tool approval card. That one's schema arrives
 * over the WebSocket as JSON Schema and is converted; this one is Zod already,
 * generated from the backend's OpenAPI document. Either way the fields, their
 * types, which are required and their validation come from the schema the
 * server itself published, so this form cannot ask for something the API will
 * reject - and adding a field to the serializer puts it on this form as soon as
 * the client is regenerated.
 */
export function NewTicketForm({
  onCreated,
}: {
  onCreated: (t: Ticket) => void;
}) {
  const [errors, setErrors] = useState<ApiFieldError[]>([]);
  const [failed, setFailed] = useState(false);

  return (
    <div className="border-b px-4 py-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
        New ticket
      </h3>

      <AutoForm
        schema={schemas.TicketCreateRequest}
        apiErrors={errors}
        fieldConfig={{
          description: { fieldType: 'textarea' },
        }}
        onSubmit={async (values) => {
          setErrors([]);
          setFailed(false);
          try {
            onCreated(await api.post('/api/tickets/', values));
          } catch (error) {
            // Field errors land on their fields; anything else is one line.
            const fields = fieldErrors(errorBody(error));
            if (fields.length) setErrors(fields);
            else setFailed(true);
          }
        }}
      >
        {failed && (
          <p className="text-xs text-red-600">
            That ticket could not be created.
          </p>
        )}
        <AutoFormSubmit className="w-full rounded bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-40">
          Create ticket
        </AutoFormSubmit>
      </AutoForm>
    </div>
  );
}
