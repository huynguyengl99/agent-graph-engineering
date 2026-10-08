/**
 * What the customer sees.
 *
 * The same app as the console, and the same components where they fit. What
 * differs is not styling but scope: the API serves this account its own tickets
 * and the public half of each thread, so there is nothing here to hide.
 */

import { Link, Outlet, useParams, useNavigate } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { LoginForm } from '@/components/LoginForm';
import { NewTicketDialog } from '@/components/NewTicketDialog';
import { PortalThread } from '@/components/PortalThread';
import { awaitingFirstReply } from '@/lib/newTickets';
import type { Ticket } from '@/lib/types';

export function PortalLayout() {
  const { fetchUser, logout, isAuthenticated, user } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const { ticketId } = useParams({ strict: false });
  const [composing, setComposing] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    void fetchUser();
  }, [fetchUser]);

  useEffect(() => {
    if (!isAuthenticated) return;
    let ignore = false;
    void (async () => {
      try {
        const page = await api.get('/api/tickets/');
        if (!ignore) setTickets(page.results ?? []);
      } catch {
        if (!ignore) setTickets([]);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [isAuthenticated]);

  if (!isAuthenticated) return <LoginForm />;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b bg-white px-4 py-3 sm:px-6">
        <span className="font-semibold">Support</span>
        {user?.isStaff && (
          <Link to="/" className="text-sm text-indigo-700 hover:underline">
            Back to the console
          </Link>
        )}
        <span className="ml-auto truncate text-sm text-gray-600">
          {user?.email}
        </span>
        <button
          onClick={() => void logout()}
          className="text-sm text-indigo-700 hover:underline"
        >
          Sign out
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          className={`w-full shrink-0 overflow-y-auto border-r bg-white md:w-80 ${
            ticketId ? 'hidden md:block' : ''
          }`}
        >
          <div className="border-b px-4 py-3">
            <button
              onClick={() => setComposing(true)}
              className="w-full rounded bg-indigo-600 px-3 py-2 text-sm text-white"
            >
              New ticket
            </button>
          </div>
          <ul>
            {tickets.map((ticket) => (
              <li key={ticket.id} className="border-b">
                <Link
                  to="/portal/tickets/$ticketId"
                  params={{ ticketId: ticket.id }}
                  className={`block px-4 py-3 hover:bg-gray-50 ${
                    ticketId === ticket.id ? 'bg-indigo-50' : ''
                  }`}
                >
                  <p className="truncate font-medium">{ticket.title}</p>
                  <p className="mt-0.5 text-xs uppercase tracking-wide text-gray-500">
                    {ticket.status}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </aside>

        {/* One pane at a time below md: the list and a thread side by side
            leave neither readable on a phone. */}
        <main
          className={`min-w-0 flex-1 bg-gray-50 ${ticketId ? '' : 'hidden md:block'}`}
        >
          <Outlet />
        </main>
      </div>

      {composing && (
        <NewTicketDialog
          onClose={() => setComposing(false)}
          onCreated={(ticket) => {
            setComposing(false);
            awaitingFirstReply.add(ticket.id);
            setTickets((current) => [ticket, ...current]);
            void navigate({
              to: '/portal/tickets/$ticketId',
              params: { ticketId: ticket.id },
            });
          }}
        />
      )}
    </div>
  );
}

export function PortalIndex() {
  return (
    <p className="p-8 text-gray-500">
      Pick one of your tickets, or report a new problem.
    </p>
  );
}

export function PortalTicketRoute({ ticketId }: { ticketId: string }) {
  return <PortalThread ticketId={ticketId} />;
}
