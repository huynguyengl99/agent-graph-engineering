import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorBody, fieldErrors } from '@/lib/apiErrors';
import type { Ticket } from '@/lib/types';

const PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const;

export function NewTicketDialog({
  onCreated,
  onClose,
}: {
  onCreated: (ticket: Ticket) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [priority, setPriority] =
    useState<(typeof PRIORITIES)[number]>('medium');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const first = useRef<HTMLInputElement>(null);

  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim()) return;
    setSending(true);
    setError(null);
    try {
      onCreated(
        await api.post('/api/tickets/', {
          title: title.trim(),
          description: message.trim(),
          priority,
        }),
      );
    } catch (caught) {
      const fields = fieldErrors(errorBody(caught));
      setError(fields[0]?.error ?? 'That ticket could not be created.');
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
    >
      <form
        onSubmit={(e) => void submit(e)}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="New ticket"
        className="w-full max-w-lg space-y-4 rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 className="text-lg font-semibold">What do you need help with?</h2>

        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Subject</span>
          <input
            ref={first}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Charged twice this month"
            className="w-full rounded border px-3 py-2"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Message</span>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={5}
            placeholder="Tell us what happened…"
            className="w-full rounded border px-3 py-2"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Priority</span>
          <select
            value={priority}
            onChange={(e) =>
              setPriority(e.target.value as (typeof PRIORITIES)[number])
            }
            className="w-full rounded border px-3 py-2"
          >
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={sending || !title.trim() || !message.trim()}
            className="rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40"
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </form>
    </div>
  );
}
