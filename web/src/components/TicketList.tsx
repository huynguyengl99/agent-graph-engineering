import { Link } from '@tanstack/react-router';
import type { Ticket } from '@/lib/types';

interface Props {
  tickets: Ticket[];
  selectedId: string | null;
}

export function TicketList({ tickets, selectedId }: Props) {
  if (tickets.length === 0) {
    return (
      <p className="px-4 py-6 text-sm text-gray-500">
        No tickets yet. Create one in the Django admin at <code>/admin/</code>.
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
              <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-500">
                {ticket.status} · {ticket.priority}
              </p>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
