import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useConversation } from '@/hooks/useConversation';
import { ChatMessageItem } from './ChatMessageItem';
import { ToolApprovalCard } from './ToolApprovalCard';
import type { ChatMessage, Conversation } from '@/lib/types';

/**
 * The rep's side of the desk. Nothing here is customer-visible, which is why
 * there is no approval gate: the only way out is `Send to ticket`, and that
 * lands on the ticket's own gate.
 */
export function ConversationPane({
  conversation,
}: {
  conversation: Conversation;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const conversationId = String(conversation.id);
  const ticketId = conversation.ticket ? String(conversation.ticket) : null;

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const page = await api.get(
          '/api/conversations/:conversationPk/messages/',
          {
            params: { conversationPk: conversationId },
          },
        );
        if (!ignore) setMessages(page.results ?? []);
      } catch {
        if (!ignore) setError('Could not load this conversation.');
      }
    })();
    return () => {
      ignore = true;
    };
  }, [conversationId]);

  const onMessage = useCallback((message: ChatMessage) => {
    setMessages((current) =>
      current.some((m) => m.id === message.id)
        ? current
        : [...current, message],
    );
  }, []);

  const { ask, sendToTicket, decideTool, pendingTool, streaming, isReady } =
    useConversation({
      conversationId,
      onMessage,
    });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming, pendingTool]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    ask(content);
    setDraft('');
  };

  const lastAnswer = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant');

  return (
    <section className="flex h-full flex-col">
      <header className="border-b bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">
            {conversation.title || 'Assistant'}
          </h2>
          {ticketId && (
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs uppercase tracking-wide text-gray-600">
              about a ticket
            </span>
          )}
          <span
            className={`ml-auto text-xs ${
              isReady ? 'text-green-600' : 'text-gray-400'
            }`}
          >
            {isReady ? 'live' : 'connecting…'}
          </span>
        </div>
        <p className="mt-2 text-sm text-gray-600">
          Internal. Nothing here reaches the customer until you send it to the
          ticket, where it still needs approval.
        </p>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        <ul className="space-y-3">
          {messages.map((message) => (
            <ChatMessageItem key={message.id} message={message} />
          ))}
          {streaming && (
            <ChatMessageItem
              pending
              message={{
                id: 'streaming',
                role: 'assistant',
                content: streaming,
                createdAt: new Date().toISOString(),
              }}
            />
          )}
        </ul>

        {pendingTool && (
          <ToolApprovalCard
            proposal={pendingTool}
            onDecide={decideTool}
            disabled={!isReady}
          />
        )}

        {ticketId && lastAnswer && !streaming && (
          <button
            onClick={() => sendToTicket(ticketId, lastAnswer.content)}
            className="rounded border border-amber-400 bg-amber-50 px-4 py-2 text-sm text-amber-900 hover:bg-amber-100"
          >
            Send this to the ticket (still needs approval)
          </button>
        )}

        <div ref={bottom} />
      </div>

      <form
        onSubmit={submit}
        className="flex gap-2 border-t bg-white px-6 py-4"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask the assistant…"
          className="flex-1 rounded border px-3 py-2"
        />
        <button
          type="submit"
          disabled={!isReady || !draft.trim()}
          className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </section>
  );
}
