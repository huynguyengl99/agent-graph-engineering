/**
 * The customer's view of their own ticket.
 *
 * No approval panel, no internal notes, no assistant: the API does not serve
 * them here, so this does not have to filter. What it posts is always public -
 * it is their ticket, and they are talking to the people answering it.
 */

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useTicketChat } from '@/hooks/useTicketChat';
import { Row, TicketEventItem } from '@/components/TicketEventItem';
import { awaitingFirstReply } from '@/lib/newTickets';
import { mergeEvents } from '@/lib/eventList';
import type { Ticket, TicketEvent } from '@/lib/types';

export function PortalThread({ ticketId }: { ticketId: string }) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [draft, setDraft] = useState('');
  const bottom = useRef<HTMLDivElement>(null);

  const { sendMessage, askAgent, isConnected } = useTicketChat({
    ticketId,
    onNewEvent: (event) =>
      setEvents((current) => mergeEvents(current, [event])),
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
  }, [events]);

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
      <header className="border-b bg-white px-6 py-4">
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
