import type { TicketEvent } from '@/lib/types';

/**
 * The payoff of the polymorphic contract: `eventType` is a literal, so
 * TypeScript narrows each branch and a new event type added on the backend
 * becomes a compile error here after `pnpm gen:all`.
 */
export function TicketEventItem({ event }: { event: TicketEvent }) {
  const when = new Date(event.createdAt).toLocaleTimeString();
  const who = event.createdBy?.fullName || event.createdBy?.email;

  switch (event.eventType) {
    case 'comment': {
      const internal = event.visibility === 'internal';
      return (
        <Row
          tone={internal ? 'internal' : 'neutral'}
          label={who || 'Someone'}
          when={when}
          badge={internal ? 'Internal note' : undefined}
          indented={internal}
        >
          {event.content}
        </Row>
      );
    }

    case 'ai_response': {
      const internal = event.visibility === 'internal';
      return (
        <Row
          tone={internal ? 'agentInternal' : 'agent'}
          label={`Agent (${event.modelName})`}
          when={when}
          badge={internal ? 'Internal' : undefined}
          indented={internal}
        >
          {event.content}
        </Row>
      );
    }

    case 'status_change':
      return (
        <Row tone="meta" label="Status" when={when}>
          {event.oldStatus} → {event.newStatus}
        </Row>
      );

    case 'assignment':
      return (
        <Row tone="meta" label="Assignment" when={when}>
          {event.newAssignee?.fullName ?? 'Unassigned'}
        </Row>
      );

    case 'handoff':
      return (
        <Row tone="meta" label={HANDLING[event.handling].title} when={when}>
          {event.reason || HANDLING[event.handling].blurb(who)}
        </Row>
      );
  }
}

export const HANDLING = {
  agent: {
    title: 'The assistant is answering',
    chip: 'Assistant',
    // Read by the customer too, so it says who they are talking to rather than
    // which internal lever someone pulled.
    blurb: () => 'Replies will come from the support assistant.',
    tone: 'bg-indigo-50 text-indigo-700',
    /** The action the other state offers. */
    action: 'Take over from the assistant',
  },
  needs_human: {
    title: 'Passed to the support team',
    chip: 'Needs a person',
    blurb: () => 'Someone on the team will follow up here.',
    tone: 'bg-amber-100 text-amber-800',
    action: 'Hand back to the assistant',
  },
  with_staff: {
    title: 'A person is answering',
    chip: 'With the team',
    blurb: (who?: string) => `${who ?? 'A colleague'} is answering this.`,
    tone: 'bg-emerald-100 text-emerald-800',
    action: 'Hand back to the assistant',
  },
} as const;

const TONES = {
  neutral: 'bg-white border-gray-200',
  // Amber, and not subtly: the cost of mistaking one for a reply is a colleague's
  // aside reaching the customer.
  internal: 'bg-amber-50 border-amber-300',
  agent: 'bg-indigo-50 border-indigo-200',
  agentInternal: 'bg-indigo-50/60 border-amber-300',
  meta: 'bg-gray-50 border-gray-200 text-gray-600 text-sm',
} as const;

export function Row({
  tone,
  label,
  when,
  badge,
  indented,
  children,
}: {
  tone: keyof typeof TONES;
  label: string;
  when: string;
  badge?: string;
  /** The team's half of the thread, stepped in so one list still reads as two
   *  conversations. */
  indented?: boolean;
  children: React.ReactNode;
}) {
  return (
    <li
      className={`rounded-lg border px-4 py-3 ${TONES[tone]} ${
        indented ? 'ml-10 border-l-4 border-l-amber-400' : ''
      }`}
    >
      <div className="flex items-baseline justify-between gap-4">
        <span className="font-medium">
          {label}
          {badge && (
            <span className="ml-2 rounded bg-amber-200 px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-amber-900">
              {badge}
            </span>
          )}
        </span>
        <span className="text-xs text-gray-500">{when}</span>
      </div>
      <p className="mt-1 whitespace-pre-wrap">{children}</p>
    </li>
  );
}
