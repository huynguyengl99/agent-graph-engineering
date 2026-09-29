/**
 * The agent's diagram endpoints, proxied at /agent in development.
 *
 * Not part of the generated OpenAPI client: these belong to the agent
 * service, which the browser does not otherwise talk to.
 */

export interface GraphSummary {
  name: string;
  subgraph: boolean;
  summary: string;
}

export async function listGraphs(): Promise<GraphSummary[]> {
  const response = await fetch('/agent/graphs');
  if (!response.ok) throw new Error(`agent returned ${response.status}`);
  const body = (await response.json()) as { graphs: GraphSummary[] };
  return body.graphs;
}

export async function fetchDiagram(name: string, xray: boolean): Promise<string> {
  const response = await fetch(`/agent/graphs/${name}.mermaid?xray=${xray}`);
  if (!response.ok) throw new Error(`agent returned ${response.status}`);
  return response.text();
}
