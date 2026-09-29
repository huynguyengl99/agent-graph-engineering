import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useTicketChat, type AgentStage } from '@/hooks/useTicketChat';
import type { Ticket, TicketEvent } from '@/lib/types';
import { TicketEventItem } from './TicketEventItem';
import { ApprovalPanel } from './ApprovalPanel';

interface Progress {
  stage: AgentStage;
  detail: string;
}

export function TicketDetail({ ticket }: { ticket: Ticket }) {
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [draft, setDraft] = useState('');
  const [pendingApproval, setPendingApproval] = useState<string | null>(null);
  const [findings, setFindings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const ticketId = String(ticket.id);

  useEffect(() => {
    // `ignore` drops the response if the user switched tickets mid-flight.
    let ignore = false;
    void (async () => {
      try {
        const page = await api.get('/api/tickets/:ticketPk/events/', {
          params: { ticketPk: ticketId },
        });
        if (!ignore) setEvents(page.results ?? []);
      } catch {
        if (!ignore) setError('Could not load the ticket history.');
      }
    })();
    return () => {
      ignore = true;
    };
  }, [ticketId]);

  const onNewEvent = useCallback((event: TicketEvent) => {
    setEvents((current) => [...current, event]);
    if (event.eventType === 'ai_response') {
      // The reply went out: the trail and the gate have served their purpose.
      setProgress([]);
      setPendingApproval(null);
    }
  }, []);

  const onApprovalRequired = useCallback((text: string, found: string[]) => {
    setPendingApproval(text);
    setFindings(found);
  }, []);

  const onAgentProgress = useCallback((stage: AgentStage, detail: string) => {
    setProgress((current) => [...current, { stage, detail }]);
  }, []);

  const { sendMessage, submitApproval, isConnected } = useTicketChat({
    ticketId,
    onNewEvent,
    onAgentProgress,
    onApprovalRequired,
  });

  const decide = useCallback(
    (approved: boolean, content?: string) => {
      submitApproval(approved, content);
      setPendingApproval(null);
      if (!approved) {
        setProgress((current) => [
          ...current,
          { stage: 'decided', detail: 'Draft rejected. Nothing was sent.' },
        ]);
      }
    },
    [submitApproval]
  );

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events, progress, pendingApproval]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    sendMessage(content);
    setDraft('');
  };

  return (
    <section className="flex h-full flex-col">
      <header className="border-b bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">{ticket.title}</h2>
          <Badge>{ticket.status}</Badge>
          <Badge>{ticket.priority}</Badge>
          <span
            className={`ml-auto text-xs ${
              isConnected ? 'text-green-600' : 'text-gray-400'
            }`}
          >
            {isConnected ? 'live' : 'connecting…'}
          </span>
        </div>
        <p className="mt-2 text-gray-700">{ticket.description}</p>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        <ul className="space-y-3">
          {events.map((event) => (
            <TicketEventItem key={`${event.eventType}-${event.id}`} event={event} />
          ))}
        </ul>

        {progress.length > 0 && (
          <ul className="space-y-2">
            {progress.map((item, index) => (
              <li
                key={index}
                className={`rounded border-l-2 px-3 py-2 text-sm ${
                  item.stage === 'failed'
                    ? 'border-red-400 bg-red-50 text-red-800'
                    : 'border-indigo-300 bg-indigo-50/60 text-indigo-900'
                }`}
              >
                <span className="font-medium">{item.stage}</span>: {item.detail}
              </li>
            ))}
          </ul>
        )}

        {pendingApproval !== null && (
          <ApprovalPanel
            draft={pendingApproval}
            findings={findings}
            onDecide={decide}
          />
        )}

        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t bg-white px-6 py-4">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Reply to this ticket…"
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

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded bg-gray-100 px-2 py-0.5 text-xs uppercase tracking-wide text-gray-600">
      {children}
    </span>
  );
}
