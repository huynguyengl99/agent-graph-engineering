/** One run, as the chain of steps it was. */

import { useEffect, useState } from 'react';
import {
  fetchTrace,
  listRuns,
  type ModelCall,
  type NodeState,
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
                  {run.thread && (
                    <span className="truncate font-mono">
                      {run.thread.slice(0, 8)}
                    </span>
                  )}
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
        {trace && <Chain spans={trace.spans} />}
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

function Chain({ spans }: { spans: Span[] }) {
  return (
    <ol className="mt-4">
      {spans.map((span, index) => (
        <li key={`${span.name}-${index}`}>
          {index > 0 && <Arrow />}
          <SpanCard span={span} />
        </li>
      ))}
    </ol>
  );
}

const Arrow = () => (
  <p className="py-1 text-center text-xs text-gray-400" aria-hidden>
    ↓
  </p>
);

function kindOf(span: Span): keyof typeof KINDS {
  if (span.call) return 'llm';
  if (span.name.startsWith('node.')) return 'node';
  if (span.name.endsWith(' run')) return 'run';
  return 'frame';
}

const KINDS = {
  run: { bar: 'border-l-slate-500', chip: 'bg-slate-100 text-slate-700' },
  node: { bar: 'border-l-indigo-500', chip: 'bg-indigo-50 text-indigo-700' },
  llm: { bar: 'border-l-violet-500', chip: 'bg-violet-100 text-violet-700' },
  frame: { bar: 'border-l-gray-300', chip: 'bg-gray-100 text-gray-600' },
};

function SpanCard({ span }: { span: Span }) {
  const [open, setOpen] = useState(false);
  const kind = kindOf(span);
  const signal = Object.entries(span.signal);
  const noise = Object.entries(span.noise);
  const expandable =
    span.call !== null || span.state !== null || noise.length > 0;

  return (
    <div>
      <div className={`rounded border border-l-4 bg-white ${KINDS[kind].bar}`}>
        <div
          className={`flex items-center gap-2 px-3 py-2 ${
            expandable ? 'cursor-pointer' : ''
          }`}
          onClick={() => expandable && setOpen(!open)}
        >
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${KINDS[kind].chip}`}
          >
            {kind}
          </span>
          <span className="truncate font-mono text-sm font-medium">
            {span.name.replace(/^node\./, '')}
          </span>
          {signal.map(([key, value]) => (
            <span
              key={key}
              className="hidden truncate rounded bg-gray-50 px-1.5 py-0.5 text-xs text-gray-700 sm:inline"
            >
              <span className="text-gray-400">{key}</span> {value}
            </span>
          ))}
          <span className="ml-auto flex shrink-0 items-center gap-2 text-xs text-gray-500">
            {span.duration_ms.toFixed(1)}ms
            {expandable && (
              <span className="text-gray-400">{open ? '▾' : '▸'}</span>
            )}
          </span>
        </div>

        {open && (
          <div className="border-t px-3 py-3">
            {span.state && <State state={span.state} />}
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
      </div>

      {span.children.length > 0 && (
        <div className="ml-5 border-l border-dashed pl-5">
          <Arrow />
          <Chain spans={span.children} />
        </div>
      )}
    </div>
  );
}

function State({ state }: { state: NodeState }) {
  return (
    <div className="mb-2 space-y-2 rounded border bg-white p-3">
      {state.update && (
        <Block label="State update" body={pretty(state.update)} accent />
      )}
      {state.state && (
        <Block label="State in" body={pretty(state.state)} folded />
      )}
    </div>
  );
}

function pretty(body: string): string {
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}

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
