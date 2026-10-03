/**
 * The agent's trace endpoints, proxied at /agent.
 *
 * Not part of the generated OpenAPI client: these belong to the agent service,
 * which owns the spans. It splits each span's attributes into the ones worth
 * reading and the rest, because which OpenTelemetry keys are noise is knowledge
 * about the tracer rather than about the page.
 */

/** What a model call was given and gave back, kept whole. */
export interface ModelCall {
  system?: string;
  input?: string;
  output?: string;
  tools?: string;
  model?: string;
  finish_reason?: string;
}

export interface Span {
  name: string;
  duration_ms: number;
  call: ModelCall | null;
  signal: Record<string, string>;
  noise: Record<string, string>;
  children: Span[];
}

export interface RunSummary {
  run_id: string;
  label: string;
  started_at: string | null;
  duration_ms: number;
  spans: number;
  calls: number;
  cost_usd: number;
  priced: boolean;
}

export interface Usage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  priced: boolean;
  unpriced_models: string[];
}

export interface Trace {
  run_id: string;
  usage: Usage;
  spans: Span[];
}

export async function listRuns(): Promise<RunSummary[]> {
  const response = await fetch('/agent/traces');
  if (!response.ok) throw new Error(`agent returned ${response.status}`);
  const body = (await response.json()) as { runs: RunSummary[] };
  return body.runs;
}

export async function fetchTrace(runId: string): Promise<Trace> {
  const response = await fetch(`/agent/traces/${runId}`);
  if (!response.ok) throw new Error(`agent returned ${response.status}`);
  return (await response.json()) as Trace;
}
