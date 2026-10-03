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
        >
          {event.content}
        </Row>
      );
    }

    case 'ai_response':
      return (
        <Row tone="agent" label={`Agent (${event.modelName})`} when={when}>
          {event.content}
        </Row>
      );

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
  }
}

const TONES = {
  neutral: 'bg-white border-gray-200',
  // Amber, and not subtly: the cost of mistaking one for a reply is a colleague's
  // aside reaching the customer.
  internal: 'bg-amber-50 border-amber-300',
  agent: 'bg-indigo-50 border-indigo-200',
  meta: 'bg-gray-50 border-gray-200 text-gray-600 text-sm',
} as const;

function Row({
  tone,
  label,
  when,
  badge,
  children,
}: {
  tone: keyof typeof TONES;
  label: string;
  when: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <li className={`rounded-lg border px-4 py-3 ${TONES[tone]}`}>
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
