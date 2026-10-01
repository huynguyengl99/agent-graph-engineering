import {
  Link,
  Outlet,
  useParams,
  useRouterState,
} from '@tanstack/react-router';
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { router } from '@/router';
import { useAuthStore } from '@/lib/auth';
import { LoginForm } from '@/components/LoginForm';
import { TicketList } from '@/components/TicketList';
import { NewTicketForm } from '@/components/NewTicketForm';
import { ConversationList } from '@/components/ConversationList';
import type { Conversation, Ticket } from '@/lib/types';

type Pane = 'tickets' | 'chat' | 'graphs' | 'settings';

export function RootLayout() {
  const { fetchUser, logout, isAuthenticated, user } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [starting, setStarting] = useState(false);
  const { ticketId, conversationId } = useParams({ strict: false });

  // The sidebar follows the route rather than its own state, so a deep link
  // opens on the right pane.
  const path = useRouterState({ select: (s) => s.location.pathname });
  const pane: Pane = path.startsWith('/chat')
    ? 'chat'
    : path.startsWith('/graphs')
      ? 'graphs'
      : path.startsWith('/settings')
        ? 'settings'
        : 'tickets';

  useEffect(() => {
    void fetchUser();
  }, [fetchUser]);

  const loadConversations = useCallback(async () => {
    try {
      const page = await api.get('/api/conversations/');
      setConversations(page.results ?? []);
    } catch {
      setConversations([]);
    }
  }, []);

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
      if (!ignore) await loadConversations();
    })();
    return () => {
      ignore = true;
    };
  }, [isAuthenticated, loadConversations]);

  const startConversation = async () => {
    setStarting(true);
    try {
      const created = await api.post('/api/conversations/', {
        title: 'New conversation',
        ticket: null,
      });
      await loadConversations();
      await router.navigate({
        to: '/chat/$conversationId',
        params: { conversationId: String(created.id) },
      });
    } finally {
      setStarting(false);
    }
  };

  if (!isAuthenticated) return <LoginForm />;

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex items-center gap-4 border-b bg-white px-6 py-3">
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
            to="/chat"
            className={`rounded px-3 py-1 ${
              pane === 'chat' ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600'
            }`}
          >
            Assistant
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
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="text-gray-600">{user?.fullName || user?.email}</span>
          <button onClick={logout} className="text-indigo-600 hover:underline">
            Sign out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Positive check: a new pane should not inherit a sidebar. */}
        {(pane === 'tickets' || pane === 'chat') && (
          <aside className="w-80 shrink-0 overflow-y-auto border-r bg-white">
            {pane === 'chat' ? (
              <ConversationList
                conversations={conversations}
                selectedId={conversationId ?? null}
                onNew={() => void startConversation()}
                busy={starting}
              />
            ) : (
              <>
                <NewTicketForm
                  onCreated={(ticket) =>
                    setTickets((current) => [ticket, ...current])
                  }
                />
                <TicketList tickets={tickets} selectedId={ticketId ?? null} />
              </>
            )}
          </aside>
        )}

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
