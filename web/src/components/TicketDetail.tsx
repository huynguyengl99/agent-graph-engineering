import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { api } from '@/lib/api';
import { useTicketChat, type AgentStage } from '@/hooks/useTicketChat';
import { mergeEvents } from '@/lib/eventList';
import type { Ticket, TicketEvent } from '@/lib/types';
import { HANDLING, Row, Thinking, TicketEventItem } from './TicketEventItem';
import { placeholdersIn } from '@/lib/placeholders';
import { publishTicketChange } from '@/lib/ticketState';
import { ApprovalPanel } from './ApprovalPanel';
import { ToolApprovalCard, type Proposal } from './ToolApprovalCard';
import { HandoverDialog } from './HandoverDialog';

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
  const [asking, setAsking] = useState(false);
  // Seeded from the ticket, so a reload finds a tool still parked at the gate.
  const [proposal, setProposal] = useState<Proposal | null>(
    parked(ticket.pendingToolCall),
  );
  const [publish, setPublish] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [thinking, setThinking] = useState({ step: '', text: '' });
  const [status, setStatus] = useState<Status>(ticket.status ?? 'open');
  const [priority, setPriority] = useState<Priority>(
    ticket.priority ?? 'medium',
  );
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
        if (!ignore)
          setEvents((current) => mergeEvents(current, page.results ?? []));
      } catch {
        if (!ignore) setError('Could not load the ticket history.');
      }
    })();
    return () => {
      ignore = true;
    };
  }, [ticketId]);

  const onNewEvent = useCallback((event: TicketEvent) => {
    setEvents((current) => mergeEvents(current, [event]));
    if (event.eventType === 'handoff') {
      setHandling(event.handling);
      publishTicketChange({ id: ticketId, handling: event.handling });
    }
    if (event.eventType === 'reasoning') setThinking({ step: '', text: '' });
    if (event.eventType === 'ai_response') {
      setAsking(false);
      setProposal(null);
    }
    if (event.eventType === 'ai_response') {
      // The reply went out: the trail and the gate have served their purpose.
      setProgress([]);
      setPendingApproval(null);
    }
    // `ticketId` is read above, so it cannot be captured from the first render:
    // moving between tickets would publish the change against the old one.
  }, [ticketId]);

  // Cleared when the finished reasoning arrives as an event of its own.
  const onReasoning = useCallback((step: string, delta: string) => {
    // A new step starts its own line rather than appending to the last one's.
    setThinking((current) =>
      current.step === step
        ? { step, text: current.text + delta }
        : { step, text: delta },
    );
  }, []);

  const onTicketUpdated = useCallback(
    (now: string, graded: string) => {
      setStatus(now as Status);
      setPriority(graded as Priority);
      publishTicketChange({
        id: ticketId,
        status: now as Status,
        priority: graded as Priority,
      });
    },
    [ticketId],
  );

  const onToolProposal = useCallback((proposed: Proposal) => {
    setProposal(proposed);
    setAsking(false);
  }, []);

  const onApprovalRequired = useCallback((text: string, found: string[]) => {
    setPendingApproval(text);
    setFindings(found);
  }, []);

  const onAgentProgress = useCallback((stage: AgentStage, detail: string) => {
    setProgress((current) => [...current, { stage, detail }]);
    if (stage === 'failed') setAsking(false);
  }, []);

  const {
    sendMessage,
    askAgent,
    setAgent,
    updateTicket,
    decideTool,
    submitApproval,
    isConnected,
  } = useTicketChat({
    ticketId,
    // The console is staff-only, so it watches the team's half too.
    team: true,
    onNewEvent,
    onAgentProgress,
    onApprovalRequired,
    onToolProposal,
    onTicketUpdated,
    onReasoning,
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
    // Everything the thread renders, or whatever is left out arrives below the
    // fold: the tool gate did, and a reviewer saw nothing to approve.
  }, [events, progress, pendingApproval, proposal, thinking]);

  const blanks = isPublic ? placeholdersIn(draft) : [];

  // Send is the one button. On a note it asks the agent, because a question
  // nobody answers is the rarer thing to want.
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content || blanks.length || asking) return;
    if (isPublic) {
      sendMessage(content, true);
    } else {
      setAsking(true);
      askAgent(false, content);
    }
    setDraft('');
  };

  const noteOnly = () => {
    const content = draft.trim();
    if (!content) return;
    sendMessage(content, false);
    setDraft('');
  };

  return (
    <section className="flex h-full flex-col">
      <header className="border-b bg-white px-4 py-4 sm:px-6">
        {/* The list is the whole screen below md, so this is the way back. */}
        <Link to="/" className="text-sm text-indigo-700 hover:underline md:hidden">
          ← All tickets
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold">{ticket.title}</h2>
          <Picker
            value={status}
            options={STATUSES}
            disabled={!isConnected}
            onChange={(next) => {
              setStatus(next as Status);
              updateTicket({ status: next });
            }}
          />
          <Picker
            value={priority}
            options={PRIORITIES}
            disabled={!isConnected}
            title="Set by the agent when it reads the ticket."
            onChange={(next) => {
              setPriority(next as Priority);
              updateTicket({ priority: next });
            }}
          />
          <span
            className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${HANDLING[handling].tone}`}
          >
            {HANDLING[handling].chip}
          </span>
          <button
            onClick={() => setSwitching(true)}
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
          {thinking.text && (
            <Thinking step={thinking.step} content={thinking.text} live />
          )}
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

        {proposal !== null && (
          <ToolApprovalCard
            proposal={proposal}
            publish={{ value: publish, onChange: setPublish }}
            onDecide={(approved, args) => {
              decideTool(approved, args, publish);
              setProposal(null);
              setAsking(approved);
            }}
          />
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

      {switching && (
        <HandoverDialog
          toAgent={handling !== 'agent'}
          onClose={() => setSwitching(false)}
          onConfirm={(message) => {
            setAgent(handling !== 'agent', message);
            setSwitching(false);
          }}
        />
      )}

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
              'Send asks the agent. Note just records it. Either way the customer sees neither.'
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
          {!isPublic && (
            <button
              type="button"
              onClick={noteOnly}
              disabled={!isConnected || !draft.trim()}
              title="Record it for the team. The agent will not answer."
              className="rounded border px-4 py-2 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
            >
              Note
            </button>
          )}
          <button
            type="submit"
            disabled={
              asking || !isConnected || !draft.trim() || blanks.length > 0
            }
            className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-40"
          >
            {asking ? 'Thinking…' : 'Send'}
          </button>
        </div>
      </form>
    </section>
  );
}

/** The REST row types its JSON fields as unknown; the card wants a shape. */
function parked(row: Ticket['pendingToolCall']): Proposal | null {
  if (!row) return null;
  return {
    tool: row.tool,
    description: row.description,
    arguments: row.arguments as Record<string, unknown>,
    argumentsSchema: row.argumentsSchema as Record<string, unknown>,
    unknownArguments: row.unknownArguments as string[],
  };
}

const STATUSES = ['open', 'in_progress', 'resolved', 'closed'] as const;
const PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const;

type Status = (typeof STATUSES)[number];
type Priority = (typeof PRIORITIES)[number];

function Picker({
  value,
  options,
  disabled,
  title,
  onChange,
}: {
  value: string;
  options: readonly string[];
  disabled?: boolean;
  title?: string;
  onChange: (value: string) => void;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      title={title}
      onChange={(e) => onChange(e.target.value)}
      className="rounded bg-gray-100 px-2 py-0.5 text-xs uppercase tracking-wide text-gray-600 disabled:opacity-50"
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {option.replace('_', ' ')}
        </option>
      ))}
    </select>
  );
}
