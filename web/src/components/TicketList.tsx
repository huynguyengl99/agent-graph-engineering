import { Link } from '@tanstack/react-router';
import type { Ticket } from '@/lib/types';
import { HANDLING } from './TicketEventItem';

interface Props {
  tickets: Ticket[];
  selectedId: string | null;
}

export function TicketList({ tickets, selectedId }: Props) {
  if (tickets.length === 0) {
    return (
      <p className="px-4 py-6 text-sm text-gray-500">
        No tickets yet. Create one above.
      </p>
    );
  }

  return (
    <ul className="divide-y">
      {tickets.map((ticket) => {
        const id = String(ticket.id);
        return (
          <li key={id}>
            <Link
              to="/tickets/$ticketId"
              params={{ ticketId: id }}
              className={`block w-full px-4 py-3 text-left hover:bg-gray-50 ${
                selectedId === id ? 'bg-indigo-50' : ''
              }`}
            >
              <p className="truncate font-medium">{ticket.title}</p>
              <p className="mt-0.5 flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
                <span>
                  {ticket.status} · {ticket.priority}
                </span>
                {ticket.handling !== 'agent' && (
                  <span
                    className={`rounded px-1.5 py-0.5 font-semibold ${HANDLING[ticket.handling].tone}`}
                  >
                    {HANDLING[ticket.handling].chip}
                  </span>
                )}
              </p>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
