import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({ startOnLoad: false, theme: 'neutral' });

/**
 * Renders the diagram the agent generated from its own compiled graph.
 *
 * Nothing here is drawn by hand, which is the point: the picture cannot
 * disagree with the code because it is produced from it.
 */
export function GraphDiagram({ definition }: { definition: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!definition) return;
    let ignore = false;

    void (async () => {
      try {
        // A fresh id per render, or mermaid reuses a stale cached SVG.
        const { svg } = await mermaid.render(
          `graph-${Math.random().toString(36).slice(2)}`,
          definition,
        );
        if (!ignore && container.current) {
          container.current.innerHTML = svg;
          setError(null);
        }
      } catch (e) {
        if (!ignore)
          setError(e instanceof Error ? e.message : 'Could not render');
      }
    })();

    return () => {
      ignore = true;
    };
  }, [definition]);

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4">
        <p className="text-sm text-red-700">{error}</p>
        <pre className="mt-2 overflow-x-auto text-xs text-red-900">
          {definition}
        </pre>
      </div>
    );
  }

  return <div ref={container} className="[&_svg]:mx-auto [&_svg]:max-w-full" />;
}
