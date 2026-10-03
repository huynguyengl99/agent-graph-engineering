import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { router } from '@/router';
import { useTicketChat, type AgentStage } from '@/hooks/useTicketChat';
import type { Ticket, TicketEvent } from '@/lib/types';
import { HANDLING, Row, TicketEventItem } from './TicketEventItem';
import { placeholdersIn } from '@/lib/placeholders';
import { ApprovalPanel } from './ApprovalPanel';

interface Progress {
  stage: AgentStage;
  detail: string;
}

export function TicketDetail({ ticket }: { ticket: Ticket }) {
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [draft, setDraft] = useState('');
  // Internal by default: reaching the customer should be the deliberate click.
  const [isPublic, setIsPublic] = useState(false);
  // Seeded from the ticket, so a reload finds a draft still waiting at the gate
  // instead of stranding a run nobody can reach.
  const [pendingApproval, setPendingApproval] = useState<string | null>(
    ticket.pendingReply?.draft ?? null,
  );
  const [findings, setFindings] = useState<string[]>(
    ticket.pendingReply?.findings ?? [],
  );
  const [handling, setHandling] = useState(ticket.handling);
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
    if (event.eventType === 'handoff') setHandling(event.handling);
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

  const { sendMessage, askAgent, setAgent, submitApproval, isConnected } =
    useTicketChat({
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
    [submitApproval],
  );

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events, progress, pendingApproval]);

  const [openingChat, setOpeningChat] = useState(false);

  const askAssistant = async () => {
    setOpeningChat(true);
    try {
      // The conversation carries the ticket, so the assistant starts with its
      // context instead of the rep pasting it in.
      const created = await api.post('/api/conversations/', {
        title: ticket.title,
        ticket: ticketId,
      });
      await router.navigate({
        to: '/chat/$conversationId',
        params: { conversationId: String(created.id) },
      });
    } finally {
      setOpeningChat(false);
    }
  };

  const blanks = isPublic ? placeholdersIn(draft) : [];

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content || blanks.length) return;
    sendMessage(content, isPublic);
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
            className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${HANDLING[handling].tone}`}
          >
            {HANDLING[handling].chip}
          </span>
          <button
            onClick={() => setAgent(handling !== 'agent')}
            disabled={!isConnected}
            title={
              handling === 'agent'
                ? 'It answers new customer messages until you take over.'
                : 'It answers new customer messages again. The customer is told.'
            }
            className={`ml-auto rounded border px-3 py-1 text-sm disabled:opacity-40 ${
              handling === 'agent'
                ? 'border-gray-300 text-gray-700 hover:bg-gray-50'
                : 'border-indigo-300 text-indigo-700 hover:bg-indigo-50'
            }`}
          >
            {HANDLING[handling].action}
          </button>
          <button
            onClick={() => void askAssistant()}
            disabled={openingChat}
            className="rounded border px-3 py-1 text-sm text-indigo-700 hover:bg-indigo-50 disabled:opacity-40"
          >
            {openingChat ? 'Opening…' : 'Ask the assistant'}
          </button>
          <span
            className={`text-xs ${
              isConnected ? 'text-green-600' : 'text-gray-400'
            }`}
          >
            {isConnected ? 'live' : 'connecting…'}
          </span>
        </div>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        <ul className="space-y-3">
          <Row
            tone="neutral"
            label={
              ticket.createdBy?.fullName ||
              ticket.createdBy?.email ||
              'Customer'
            }
            when={new Date(ticket.createdAt).toLocaleTimeString()}
          >
            {ticket.description}
          </Row>
          {events.map((event) => (
            <TicketEventItem
              key={`${event.eventType}-${event.id}`}
              event={event}
            />
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

      <form
        onSubmit={submit}
        className={`flex flex-col gap-2 border-t px-6 py-4 ${
          isPublic ? 'bg-white' : 'bg-amber-50'
        }`}
      >
        <div className="flex items-center gap-3 text-sm">
          <div className="flex overflow-hidden rounded border">
            {([false, true] as const).map((value) => (
              <button
                key={String(value)}
                type="button"
                onClick={() => setIsPublic(value)}
                className={`px-3 py-1 text-xs ${
                  isPublic === value
                    ? value
                      ? 'bg-indigo-600 text-white'
                      : 'bg-amber-500 text-white'
                    : 'bg-white text-gray-600'
                }`}
              >
                {value ? 'Reply to customer' : 'Internal note'}
              </button>
            ))}
          </div>
          <span className="text-xs text-gray-600">
            {blanks.length > 0 ? (
              <span className="text-amber-800">
                Fill in {blanks.join(', ')} before this can go out.
              </span>
            ) : isPublic ? (
              'The customer sees this.'
            ) : (
              'Only your team sees this, the agent included.'
            )}
          </span>
        </div>
        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={
              isPublic
                ? 'Reply to the customer…'
                : 'Note for your team, or a question for the agent…'
            }
            className="flex-1 rounded border px-3 py-2"
          />
          <button
            type="button"
            onClick={() => {
              askAgent(isPublic, isPublic ? '' : draft.trim());
              if (!isPublic) setDraft('');
            }}
            disabled={!isConnected || (!isPublic && !draft.trim())}
            title={
              isPublic
                ? 'The agent answers the customer here.'
                : 'The agent drafts for your team only.'
            }
            className="rounded border px-4 py-2 text-indigo-700 hover:bg-indigo-50 disabled:opacity-40"
          >
            {isPublic ? 'Let the agent reply' : 'Ask the agent'}
          </button>
          <button
            type="submit"
            disabled={!isConnected || !draft.trim() || blanks.length > 0}
            className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-40"
          >
            Send
          </button>
        </div>
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
