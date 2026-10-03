import { placeholdersIn } from '@/lib/placeholders';

export function PlaceholderForm({
  text,
  values,
  onChange,
}: {
  text: string;
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}) {
  const names = placeholdersIn(text);
  if (!names.length) return null;

  return (
    <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
        {names.length} value{names.length === 1 ? '' : 's'} to fill in
      </p>
      <p className="mt-1 text-xs text-amber-900">
        The agent left these blank rather than guessing. Nothing goes out until
        they are filled.
      </p>
      <div className="mt-2 space-y-2">
        {names.map((name) => (
          <label key={name} className="flex items-center gap-2 text-sm">
            <span className="w-40 shrink-0 font-mono text-xs text-amber-900">
              {name}
            </span>
            <input
              value={values[name] ?? ''}
              onChange={(e) => onChange({ ...values, [name]: e.target.value })}
              className="flex-1 rounded border px-2 py-1"
            />
          </label>
        ))}
      </div>
    </div>
  );
}
