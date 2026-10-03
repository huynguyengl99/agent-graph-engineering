/**
 * One run, as a tree.
 *
 * Here rather than behind the Django admin: the person asking "why did it answer
 * that?" is the person who just watched it answer, and they are already in this
 * app. The agent serves the spans as JSON and this renders them, so there is one
 * renderer rather than one here and one there.
 */

import { useEffect, useState } from 'react';
import { fetchTrace, listRuns, type Span, type Trace } from '@/lib/traces';

export function TracesRoute() {
  const [runs, setRuns] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const found = await listRuns();
        if (ignore) return;
        setRuns(found);
        setSelected((current) => current ?? found[0] ?? null);
      } catch (e) {
        if (!ignore)
          setError(e instanceof Error ? e.message : 'Agent unreachable');
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let ignore = false;
    void (async () => {
      try {
        const found = await fetchTrace(selected);
        if (!ignore) setTrace(found);
      } catch (e) {
        if (!ignore)
          setError(e instanceof Error ? e.message : 'Agent unreachable');
      }
    })();
    return () => {
      ignore = true;
    };
  }, [selected]);

  if (error) return <p className="p-8 text-red-600">{error}</p>;
  if (!runs.length)
    return (
      <p className="p-8 text-gray-500">
        No runs traced yet. Work a ticket or ask the assistant something.
      </p>
    );

  return (
    <div className="flex h-full">
      <aside className="w-72 overflow-y-auto border-r bg-white">
        <h2 className="border-b px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
          {runs.length} run{runs.length === 1 ? '' : 's'}
        </h2>
        <ul>
          {runs.map((run) => (
            <li key={run} className="border-b">
              <button
                onClick={() => setSelected(run)}
                className={`block w-full px-4 py-2 text-left font-mono text-xs hover:bg-gray-50 ${
                  selected === run ? 'bg-indigo-50' : ''
                }`}
              >
                {run.slice(0, 18)}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section
        className="min-w-0 flex-1 overflow-y-auto p-6"
        aria-label="trace"
      >
        {trace && <Cost trace={trace} />}
        <ul className="mt-4 space-y-1">
          {trace?.spans.map((span, index) => (
            <SpanRow key={`${span.name}-${index}`} span={span} depth={0} />
          ))}
        </ul>
      </section>
    </div>
  );
}

function Cost({ trace }: { trace: Trace }) {
  const { usage } = trace;
  return (
    <div className="flex flex-wrap gap-6 rounded border bg-white px-4 py-3 text-sm">
      <Stat label="run" value={trace.run_id.slice(0, 18)} mono />
      <Stat label="model calls" value={String(usage.calls)} />
      <Stat label="tokens" value={usage.total_tokens.toLocaleString()} />
      <Stat
        label="cost"
        value={
          usage.priced
            ? `$${usage.cost_usd.toFixed(4)}`
            : `unpriced (${usage.unpriced_models.join(', ')})`
        }
      />
    </div>
  );
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-gray-500">{label}</p>
      <p className={mono ? 'font-mono text-xs' : ''}>{value}</p>
    </div>
  );
}

function SpanRow({ span, depth }: { span: Span; depth: number }) {
  const [open, setOpen] = useState(false);
  const signal = Object.entries(span.signal);
  const noise = Object.entries(span.noise);

  return (
    <li>
      <div
        className="flex items-baseline gap-3 rounded px-2 py-1 hover:bg-white"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
      >
        <span className="font-mono text-sm">{span.name}</span>
        <span className="text-xs text-gray-500">
          {span.duration_ms.toFixed(1)}ms
        </span>
        {signal.map(([key, value]) => (
          <span key={key} className="text-xs text-gray-700">
            <span className="text-gray-500">{key}</span> {value}
          </span>
        ))}
        {noise.length > 0 && (
          <button
            onClick={() => setOpen(!open)}
            className="text-xs text-indigo-700 hover:underline"
          >
            {open ? 'less' : `+${noise.length}`}
          </button>
        )}
      </div>

      {open && (
        <dl
          className="mb-1 space-y-0.5 text-xs text-gray-600"
          style={{ paddingLeft: `${depth * 20 + 24}px` }}
        >
          {noise.map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <dt className="text-gray-500">{key}</dt>
              <dd className="font-mono">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {span.children.length > 0 && (
        <ul>
          {span.children.map((child, index) => (
            <SpanRow
              key={`${child.name}-${index}`}
              span={child}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
