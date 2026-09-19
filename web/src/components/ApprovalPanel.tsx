import { useState } from 'react';

interface Props {
  draft: string;
  onDecide: (approved: boolean, content?: string) => void;
}

/**
 * The human gate. Until someone acts here the graph stays parked in the
 * agent's checkpointer and nothing reaches the customer.
 */
export function ApprovalPanel({ draft, onDecide }: Props) {
  const [content, setContent] = useState(draft);
  const edited = content.trim() !== draft.trim();

  return (
    <section className="rounded-lg border-2 border-amber-300 bg-amber-50 p-4">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold text-amber-900">Reply awaiting approval</h3>
        <span className="rounded bg-amber-200 px-2 py-0.5 text-xs text-amber-900">
          not sent yet
        </span>
      </div>

      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={5}
        className="mt-3 w-full rounded border border-amber-300 bg-white px-3 py-2 text-sm"
      />

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => onDecide(true, edited ? content : undefined)}
          className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
        >
          {edited ? 'Send edited reply' : 'Approve and send'}
        </button>
        <button
          onClick={() => onDecide(false)}
          className="rounded border border-amber-400 px-4 py-2 text-sm text-amber-900 hover:bg-amber-100"
        >
          Reject
        </button>
        {edited && (
          <span className="text-xs text-amber-800">edited from the draft</span>
        )}
      </div>
    </section>
  );
}
