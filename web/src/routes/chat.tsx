import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { ConversationPane } from '@/components/ConversationPane';
import type { Conversation } from '@/lib/types';

/** Loaded here, so a deep link to a conversation works on a cold page load. */
export function ChatRoute({ conversationId }: { conversationId: string }) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const found = await api.get('/api/conversations/:id/', {
          params: { id: conversationId },
        });
        if (!ignore) setConversation(found);
      } catch {
        if (!ignore) setError(true);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [conversationId]);

  if (error) {
    return <p className="p-8 text-red-600">That conversation could not be loaded.</p>;
  }
  if (!conversation) return <p className="p-8 text-gray-500">Loading…</p>;

  return <ConversationPane conversation={conversation} />;
}
