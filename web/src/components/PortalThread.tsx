/**
 * The customer's view of their own ticket.
 *
 * No approval panel, no internal notes, no assistant: the API does not serve
 * them here, so this does not have to filter. What it posts is always public -
 * it is their ticket, and they are talking to the people answering it.
 */

import { useEffect, useRef, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { api } from '@/lib/api';
import { useTicketChat } from '@/hooks/useTicketChat';
import { Markdown } from '@/components/Markdown';
import { Row, Thinking, TicketEventItem } from '@/components/TicketEventItem';
import { awaitingFirstReply } from '@/lib/newTickets';
import { mergeEvents } from '@/lib/eventList';
import type { Ticket, TicketEvent } from '@/lib/types';

export function PortalThread({ ticketId }: { ticketId: string }) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [draft, setDraft] = useState('');
  const [working, setWorking] = useState(false);
  // The reply as it arrives, replaced by the event that carries the finished one.
  const [streaming, setStreaming] = useState('');
  // What it is working on, while it works. Live only: the finished reasoning
  // stays the team's, so this is gone on reload.
  const [thinking, setThinking] = useState({ step: '', text: '' });
  const bottom = useRef<HTMLDivElement>(null);

  const { sendMessage, askAgent, isConnected } = useTicketChat({
    ticketId,
    onNewEvent: (event) => {
      if (event.eventType === 'reasoning') setThinking({ step: '', text: '' });
      if (event.eventType === 'ai_response') setStreaming('');
      setEvents((current) => mergeEvents(current, [event]));
    },
    onAgentWorking: (busy) => {
      setWorking(busy);
      // The only end-of-run signal they get: the events that clear this for
      // staff are internal, and a resumed run sends a reply it already wrote
      // rather than writing it again.
      if (!busy) setThinking({ step: '', text: '' });
    },
    onAnswer: (_reference, content) => {
      setThinking({ step: '', text: '' });
      setStreaming(content);
    },
    onReasoning: (step, content) => setThinking({ step, text: content }),
  });

  // The opening message is the ticket, so nothing posted it: hand it over as
  // soon as the thread is live.
  useEffect(() => {
    if (!isConnected || !awaitingFirstReply.delete(ticketId)) return;
    askAgent(true);
  }, [isConnected, ticketId, askAgent]);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      const [detail, page] = await Promise.all([
        api.get('/api/tickets/:id/', { params: { id: ticketId } }),
        api.get('/api/tickets/:ticketPk/events/', {
          params: { ticketPk: ticketId },
        }),
      ]);
      if (ignore) return;
      setTicket(detail as Ticket);
      setEvents((current) => mergeEvents(current, page.results ?? []));
    })();
    return () => {
      ignore = true;
    };
  }, [ticketId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events, working, streaming, thinking]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    sendMessage(content, true);
    setDraft('');
  };

  if (!ticket) return <p className="p-8 text-gray-500">Loading…</p>;

  return (
    <section className="flex h-full flex-col">
      <header className="border-b bg-white px-4 py-4 sm:px-6">
        {/* The list is the whole screen below md, so this is the way back. */}
        <Link
          to="/portal"
          className="text-sm text-indigo-700 hover:underline md:hidden"
        >
          ← All tickets
        </Link>
        <h2 className="text-xl font-semibold">{ticket.title}</h2>
      </header>

      <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto p-6">
        <Row
          tone="neutral"
          label={ticket.createdBy?.fullName || ticket.createdBy?.email || 'You'}
          when={new Date(ticket.createdAt).toLocaleTimeString()}
        >
          {ticket.description}
        </Row>
        {events.map((event) => (
          <TicketEventItem key={event.id} event={event} />
        ))}
        {thinking.text && !streaming && (
          <Thinking step={thinking.step} content={thinking.text} live />
        )}
        {streaming && (
          <Row tone="agent" label="Agent" when="">
            <Markdown streaming>{streaming}</Markdown>
          </Row>
        )}
        {working && !streaming && !thinking.text && (
          // Nothing about what it is doing: which step it is on and what it
          // decided are the team's. That somebody has your ticket is yours.
          <li className="flex items-center gap-2 px-4 py-3 text-sm text-gray-500">
            <span className="flex gap-1" aria-hidden>
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
            Support is looking at this…
          </li>
        )}
        <div ref={bottom} />
      </ul>

      <form
        onSubmit={submit}
        className="flex gap-2 border-t bg-white px-6 py-4"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add to this ticket…"
          className="flex-1 rounded border px-3 py-2"
        />
        <button
          type="submit"
          disabled={!isConnected || !draft.trim()}
          className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </section>
  );
}
