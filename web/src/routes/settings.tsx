import { ModelPreferences } from '@/components/ModelPreferences';

/**
 * The two generated contracts, and the one thing a user is allowed to change
 * about how the agent runs.
 */
export function SettingsRoute() {
  return (
    <div className="max-w-2xl space-y-6 p-8">
      <ModelPreferences />

      <section className="rounded-lg border bg-white p-4">
        <h3 className="text-sm font-semibold">Contracts</h3>
        <p className="mt-1 text-xs text-gray-600">
          Every client in this repo is generated from one of these. Change a
          serializer or a WebSocket message, run <code>just gen</code>, and the
          compiler says what broke.
        </p>
        <ul className="mt-3 space-y-2 text-sm">
          {[
            ['REST, as Swagger UI', '/api/schema/swg/'],
            ['The backend’s WebSocket messages', '/api/asyncapi/docs/'],
            ['The agent’s WebSocket messages', '/agent/asyncapi'],
          ].map(([label, href]) => (
            <li key={href}>
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-600 hover:underline"
              >
                {label}
              </a>
              <code className="ml-2 text-xs text-gray-500">{href}</code>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
