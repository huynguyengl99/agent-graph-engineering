/**
 * One run, as a tree, with what each model call was actually given.
 *
 * Here rather than behind the Django admin: whoever asks why it answered that
 * is the person who just watched it answer. The agent serves the spans and
 * decides which attributes are worth reading; this renders them.
 */

import { useEffect, useState } from 'react';
import {
  fetchTrace,
  listRuns,
  type ModelCall,
  type RunSummary,
  type Span,
  type Trace,
} from '@/lib/traces';

export function TracesRoute() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
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
        setSelected((current) => current ?? found[0]?.run_id ?? null);
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
      <aside className="w-96 shrink-0 overflow-y-auto border-r bg-white">
        <h2 className="border-b px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
          {runs.length} run{runs.length === 1 ? '' : 's'}
        </h2>
        <ul>
          {runs.map((run) => (
            <li key={run.run_id} className="border-b">
              <button
                onClick={() => setSelected(run.run_id)}
                className={`block w-full px-4 py-2.5 text-left hover:bg-gray-50 ${
                  selected === run.run_id ? 'bg-indigo-50' : ''
                }`}
              >
                <p className="truncate text-sm">{run.label || run.run_id}</p>
                <p className="mt-0.5 flex gap-3 text-xs text-gray-500">
                  <span>{when(run.started_at)}</span>
                  <span>{run.calls} calls</span>
                  <span>{money(run.cost_usd, run.priced)}</span>
                  <span>{(run.duration_ms / 1000).toFixed(1)}s</span>
                </p>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section
        className="min-w-0 flex-1 overflow-y-auto p-6"
        aria-label="trace"
      >
        {trace && <Totals trace={trace} />}
        <ul className="mt-4 space-y-0.5">
          {trace?.spans.map((span, index) => (
            <SpanRow key={`${span.name}-${index}`} span={span} depth={0} />
          ))}
        </ul>
      </section>
    </div>
  );
}

const when = (at: string | null) =>
  at ? new Date(at).toLocaleTimeString() : '';

const money = (usd: number, priced: boolean) =>
  priced ? `$${usd.toFixed(4)}` : 'unpriced';

function Totals({ trace }: { trace: Trace }) {
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
  const expandable = span.call !== null || noise.length > 0;

  return (
    <li>
      <div
        className={`flex items-baseline gap-3 rounded px-2 py-1 ${
          expandable ? 'cursor-pointer hover:bg-white' : ''
        }`}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={() => expandable && setOpen(!open)}
      >
        {span.call && (
          <span className="rounded bg-violet-100 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700">
            llm
          </span>
        )}
        <span className="font-mono text-sm">{span.name}</span>
        <span className="text-xs text-gray-500">
          {span.duration_ms.toFixed(1)}ms
        </span>
        {signal.map(([key, value]) => (
          <span key={key} className="truncate text-xs text-gray-700">
            <span className="text-gray-500">{key}</span> {value}
          </span>
        ))}
        {expandable && (
          <span className="ml-auto shrink-0 text-xs text-indigo-700">
            {open ? '−' : span.call ? 'open' : `+${noise.length}`}
          </span>
        )}
      </div>

      {open && (
        <div style={{ paddingLeft: `${depth * 20 + 24}px` }} className="mb-2">
          {span.call && <Call call={span.call} />}
          {noise.length > 0 && (
            <dl className="mt-2 space-y-0.5 text-xs text-gray-600">
              {noise.map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <dt className="shrink-0 text-gray-500">{key}</dt>
                  <dd className="truncate font-mono">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
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

/** What the model was sent and what came back, in full. */
function Call({ call }: { call: ModelCall }) {
  return (
    <div className="space-y-2 rounded border bg-white p-3">
      {call.system && <Block label="System prompt" body={call.system} folded />}
      {call.input && <Block label="Input" body={call.input} />}
      {call.tools && <Block label="Tools offered" body={call.tools} folded />}
      {call.output && <Block label="Response" body={call.output} accent />}
    </div>
  );
}

function Block({
  label,
  body,
  folded,
  accent,
}: {
  label: string;
  body: string;
  folded?: boolean;
  accent?: boolean;
}) {
  const [open, setOpen] = useState(!folded);
  return (
    <div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setOpen(!open)}
          className={`text-xs font-semibold uppercase tracking-wide ${
            accent ? 'text-green-700' : 'text-gray-500'
          }`}
        >
          {open ? '▾' : '▸'} {label}{' '}
          <span className="font-normal normal-case text-gray-400">
            ({body.length.toLocaleString()} chars)
          </span>
        </button>
        <button
          onClick={() => void navigator.clipboard?.writeText(body)}
          className="rounded border px-1.5 text-xs text-gray-600 hover:bg-gray-50"
        >
          Copy
        </button>
      </div>
      {open && (
        <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-gray-50 p-2 text-xs">
          {body}
        </pre>
      )}
    </div>
  );
}
