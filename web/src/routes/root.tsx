import {
  Link,
  Navigate,
  Outlet,
  useParams,
  useRouterState,
} from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { LoginForm } from '@/components/LoginForm';
import { TicketList } from '@/components/TicketList';
import { onTicketChange } from '@/lib/ticketState';
import type { Ticket } from '@/lib/types';

type Pane = 'tickets' | 'graphs' | 'traces' | 'settings';

export function RootLayout() {
  const { fetchUser, logout, isAuthenticated, user } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const { ticketId } = useParams({ strict: false });

  // The sidebar follows the route rather than its own state, so a deep link
  // opens on the right pane.
  const path = useRouterState({ select: (s) => s.location.pathname });
  const pane: Pane = path.startsWith('/graphs')
    ? 'graphs'
    : path.startsWith('/traces')
      ? 'traces'
      : path.startsWith('/settings')
        ? 'settings'
        : 'tickets';

  // The ticket being read tells the list what changed, rather than every row
  // holding a subscription of its own.
  useEffect(
    () =>
      onTicketChange((patch) =>
        setTickets((current) =>
          current.map((ticket) =>
            String(ticket.id) === patch.id ? { ...ticket, ...patch } : ticket,
          ),
        ),
      ),
    [],
  );

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
  // The console is for people answering tickets. Everyone else has a portal.
  if (user && !user.isStaff) return <Navigate to="/portal" />;

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b bg-white px-4 py-3 sm:px-6">
        <h1 className="font-semibold">Agent Graph Engineering</h1>
        <nav className="flex gap-1 text-sm">
          <Link
            to="/"
            className={`rounded px-3 py-1 ${
              pane === 'tickets'
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-gray-600'
            }`}
          >
            Tickets
          </Link>
          <Link
            to="/graphs"
            className={`rounded px-3 py-1 ${
              pane === 'graphs'
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-gray-600'
            }`}
          >
            Graphs
          </Link>
          <Link
            to="/traces"
            className={`rounded px-3 py-1 ${
              pane === 'traces'
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-gray-600'
            }`}
          >
            Traces
          </Link>
          <Link
            to="/settings"
            className={`rounded px-3 py-1 ${
              pane === 'settings'
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-gray-600'
            }`}
          >
            Settings
          </Link>
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-3 text-sm">
          <span className="truncate text-gray-600">{user?.fullName || user?.email}</span>
          <button onClick={logout} className="text-indigo-600 hover:underline">
            Sign out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Positive check: a new pane should not inherit a sidebar. */}
        {pane === 'tickets' && (
          <aside
            className={`w-full shrink-0 overflow-y-auto border-r bg-white md:w-80 ${
              ticketId ? 'hidden md:block' : ''
            }`}
          >
            <TicketList tickets={tickets} selectedId={ticketId ?? null} />
          </aside>
        )}

        {/* One pane at a time below md: 320px of list beside a thread does not
            fit a phone, and shrinking both leaves neither readable. */}
        <main
          className={`min-w-0 flex-1 ${
            pane === 'tickets' && !ticketId ? 'hidden md:block' : ''
          }`}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
