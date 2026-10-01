import { useEffect, useState } from 'react';
import {
  AutoForm,
  AutoFormSubmit,
  type ApiFieldError,
} from '@/components/auto-form';
import { schemas } from '@/schemas/backend';
import { api } from '@/lib/api';
import { errorBody, fieldErrors } from '@/lib/apiErrors';
import type { z } from 'zod';

type Preference = z.infer<typeof schemas.ModelPreference>;

/**
 * Pick the model that fills each purpose.
 *
 * The purposes are system config and the models are user config, which is what
 * makes provider independence real rather than theoretical. The form is the same
 * `AutoForm` the tool approval card uses: `purpose` renders as a select because
 * the server declared it an enum, and `provider:name` is validated server-side,
 * so a bad value lands on its own field.
 */
export function ModelPreferences() {
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [errors, setErrors] = useState<ApiFieldError[]>([]);
  const [saved, setSaved] = useState<string | null>(null);

  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const page = await api.get('/api/preferences/model-preferences/');
        if (!ignore) setPreferences(page.results ?? []);
      } catch {
        if (!ignore) setPreferences([]);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [reloads]);

  return (
    <section className="rounded-lg border bg-white p-4">
      <h3 className="text-sm font-semibold">Models</h3>
      <p className="mt-1 text-xs text-gray-600">
        Which model fills each purpose. Unset purposes use the deployment
        default.
      </p>

      {preferences.length > 0 && (
        <ul className="mt-3 divide-y text-sm">
          {preferences.map((preference) => (
            <li
              key={preference.purpose}
              className="flex items-center justify-between py-2"
            >
              <span className="uppercase tracking-wide text-gray-500">
                {preference.purpose}
              </span>
              <code>{preference.model}</code>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3">
        <AutoForm
          schema={schemas.ModelPreferenceRequest}
          apiErrors={errors}
          fieldConfig={{
            model: {
              description: 'provider:name, e.g. anthropic:claude-sonnet-5',
            },
          }}
          onSubmit={async (values) => {
            setErrors([]);
            setSaved(null);
            try {
              const created = await api.post(
                '/api/preferences/model-preferences/',
                values,
              );
              setSaved(`${created.purpose} now uses ${created.model}`);
              setReloads((n) => n + 1);
            } catch (error) {
              setErrors(fieldErrors(errorBody(error)));
            }
          }}
        >
          {saved && <p className="text-xs text-green-700">{saved}</p>}
          <AutoFormSubmit className="w-full rounded bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-40">
            Use this model
          </AutoFormSubmit>
        </AutoForm>
      </div>
    </section>
  );
}
