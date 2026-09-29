import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { LoginForm } from '@/components/LoginForm';
import { TicketList } from '@/components/TicketList';
import { TicketDetail } from '@/components/TicketDetail';
import type { Ticket } from '@/lib/types';

function App() {
  const { fetchUser, logout, isAuthenticated, user } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<Ticket | null>(null);

  useEffect(() => {
    fetchUser();
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
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex items-center gap-4 border-b bg-white px-6 py-3">
        <h1 className="font-semibold">Agent Graph Engineering</h1>
        <span className="text-sm text-gray-500">ticket triage</span>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="text-gray-600">{user?.fullName || user?.email}</span>
          <button onClick={logout} className="text-indigo-600 hover:underline">
            Sign out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-80 shrink-0 overflow-y-auto border-r bg-white">
          <TicketList
            tickets={tickets}
            selectedId={selected ? String(selected.id) : null}
            onSelect={setSelected}
          />
        </aside>

        <main className="min-w-0 flex-1">
          {selected ? (
            <TicketDetail key={String(selected.id)} ticket={selected} />
          ) : (
            <p className="p-8 text-gray-500">
              Pick a ticket to see its history and talk to the triage agent.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
