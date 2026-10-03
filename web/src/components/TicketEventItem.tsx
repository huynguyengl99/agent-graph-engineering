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
        <Row
          tone="meta"
          label={HANDLING[event.handling].title}
          when={when}
          indented
        >
          {event.reason || HANDLING[event.handling].blurb(who)}
        </Row>
      );
  }
}

export const HANDLING = {
  agent: {
    title: 'Back to the agent',
    chip: 'Agent',
    blurb: (who?: string) => `${who ?? 'A colleague'} handed this back.`,
    tone: 'bg-indigo-50 text-indigo-700',
  },
  needs_human: {
    title: 'Handed off',
    chip: 'Needs a person',
    blurb: () => 'The agent asked for a person to take this.',
    tone: 'bg-amber-100 text-amber-800',
  },
  with_staff: {
    title: 'Taken',
    chip: 'With staff',
    blurb: (who?: string) => `${who ?? 'A colleague'} is answering this.`,
    tone: 'bg-emerald-100 text-emerald-800',
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
