import { useEffect, useState } from 'react';
import { GraphDiagram } from '@/components/GraphDiagram';
import { fetchDiagram, listGraphs, type GraphSummary } from '@/lib/graphs';

export function GraphsRoute() {
  const [graphs, setGraphs] = useState<GraphSummary[]>([]);
  // The parent, whatever it is called: a hardcoded name silently renders
  // nothing the day the graph is renamed.
  const [selected, setSelected] = useState('');
  const [xray, setXray] = useState(true);
  const [definition, setDefinition] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const found = await listGraphs();
        if (ignore) return;
        setGraphs(found);
        setSelected(
          (current) => current || found.find((g) => !g.subgraph)?.name || '',
        );
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
        const text = await fetchDiagram(selected, xray);
        if (!ignore) {
          setDefinition(text);
          setError(null);
        }
      } catch (e) {
        if (!ignore)
          setError(e instanceof Error ? e.message : 'Agent unreachable');
      }
    })();
    return () => {
      ignore = true;
    };
  }, [selected, xray]);

  const current = graphs.find((g) => g.name === selected);

  return (
    <section className="flex h-full flex-col">
      <header className="border-b bg-white px-6 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold">Graphs</h2>
          <div className="flex gap-1">
            {graphs.map((graph) => (
              <button
                key={graph.name}
                onClick={() => setSelected(graph.name)}
                className={`rounded px-3 py-1 text-sm ${
                  selected === graph.name
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {graph.name}
                {graph.subgraph && (
                  <span className="ml-1 text-xs text-gray-400">sub</span>
                )}
              </button>
            ))}
          </div>

          <label className="ml-auto flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={xray}
              onChange={(e) => setXray(e.target.checked)}
            />
            Expand subgraphs
          </label>
        </div>
        <p className="mt-2 text-sm text-gray-600">
          {current?.summary ||
            'Generated from the compiled graph, so it cannot disagree with the code.'}
        </p>
      </header>

      <div className="flex-1 overflow-auto bg-white px-6 py-6">
        {error ? (
          <p className="text-sm text-red-600">
            {error}. Is the agent running on port 8001?
          </p>
        ) : (
          <GraphDiagram definition={definition} />
        )}
      </div>
    </section>
  );
}
