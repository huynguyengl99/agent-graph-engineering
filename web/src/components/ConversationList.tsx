import { Link } from '@tanstack/react-router';
import type { Conversation } from '@/lib/types';

interface Props {
  conversations: Conversation[];
  selectedId: string | null;
  onNew: () => void;
  busy?: boolean;
}

export function ConversationList({
  conversations,
  selectedId,
  onNew,
  busy = false,
}: Props) {
  return (
    <div>
      <div className="border-b px-4 py-3">
        <button
          onClick={onNew}
          disabled={busy}
          className="w-full rounded bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-40"
        >
          {busy ? 'Starting…' : 'New conversation'}
        </button>
      </div>

      {conversations.length === 0 ? (
        <p className="px-4 py-6 text-sm text-gray-500">
          No conversations yet. Start one, or open one from a ticket.
        </p>
      ) : (
        <ul className="divide-y">
          {conversations.map((conversation) => {
            const id = String(conversation.id);
            return (
              <li key={id}>
                <Link
                  to="/chat/$conversationId"
                  params={{ conversationId: id }}
                  className={`block w-full px-4 py-3 text-left hover:bg-gray-50 ${
                    selectedId === id ? 'bg-indigo-50' : ''
                  }`}
                >
                  <p className="truncate font-medium">
                    {conversation.title || 'Untitled'}
                  </p>
                  <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-500">
                    {conversation.ticket ? 'about a ticket' : 'general'}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
