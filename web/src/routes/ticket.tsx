import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { TicketDetail } from '@/components/TicketDetail';
import type { Ticket } from '@/lib/types';

/**
 * The ticket is loaded here rather than handed down from the list, so a
 * deep link to /tickets/<id> works on a cold page load. The route keys this
 * on ticketId, so switching tickets remounts instead of resetting state.
 */
export function TicketRoute({ ticketId }: { ticketId: string }) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const found = await api.get('/api/tickets/:id/', { params: { id: ticketId } });
        if (!ignore) setTicket(found);
      } catch {
        if (!ignore) setError(true);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [ticketId]);

  if (error) return <p className="p-8 text-red-600">That ticket could not be loaded.</p>;
  if (!ticket) return <p className="p-8 text-gray-500">Loading…</p>;

  return <TicketDetail ticket={ticket} />;
}
