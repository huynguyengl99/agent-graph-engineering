import { useEffect, useRef, useState } from 'react';
import { PlaceholderForm } from './PlaceholderForm';
import { fillPlaceholders, placeholdersIn } from '@/lib/placeholders';

/** Suggested, not imposed: the point is that someone reads it before the voice
 *  answering the customer changes. */
const SUGGESTED = {
  toAgent:
    'Thanks for waiting. Our assistant will take it from here and should ' +
    'have an answer for you shortly.',
  toTeam:
    'Hi, I am {{your name}} from the support team. I will take it from here.',
};

export function HandoverDialog({
  toAgent,
  onConfirm,
  onClose,
}: {
  toAgent: boolean;
  onConfirm: (message: string) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState(
    toAgent ? SUGGESTED.toAgent : SUGGESTED.toTeam,
  );
  const [values, setValues] = useState<Record<string, string>>({});
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    box.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const filled = fillPlaceholders(text, values);
  const missing = placeholdersIn(filled);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={toAgent ? 'Hand back to the assistant' : 'Take over'}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg space-y-3 rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 className="text-lg font-semibold">
          {toAgent ? 'Hand back to the assistant?' : 'Take over this ticket?'}
        </h2>
        <p className="text-sm text-gray-600">
          {toAgent
            ? 'It will answer new customer messages until someone takes over again.'
            : 'The assistant stops replying on its own. It still answers you here.'}
        </p>

        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">
            Tell the customer (optional)
          </span>
          <textarea
            ref={box}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            className="w-full rounded border px-3 py-2"
          />
        </label>

        <PlaceholderForm text={text} values={values} onChange={setValues} />

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(filled.trim())}
            disabled={missing.length > 0}
            title={
              missing.length ? `Still blank: ${missing.join(', ')}` : undefined
            }
            className="rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40"
          >
            {toAgent ? 'Hand back' : 'Take over'}
          </button>
        </div>
      </div>
    </div>
  );
}
