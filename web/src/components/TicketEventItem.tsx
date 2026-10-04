import { useState } from 'react';
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

    case 'reasoning':
      return (
        <Thinking
          step={event.step}
          content={event.content}
          decision={event.decision}
          when={when}
        />
      );

    case 'tool_call':
      return <ToolCall event={event} when={when} />;

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

/** What each step is called, for a row that says which one thought. */
const STEPS: Record<string, string> = {
  classify: 'Filed the ticket',
  decide: 'Chose what to do',
  plan: 'Picked the tool',
  refine: 'Searched again',
};

export function Thinking({
  step,
  content,
  decision,
  when,
  live,
}: {
  step?: string;
  content: string;
  decision?: string;
  when?: string;
  /** Still being written, so it opens itself and has nothing to fold yet. */
  live?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const showing = live || open;

  return (
    <li className="ml-10 rounded-lg border border-l-4 border-gray-200 border-l-gray-300 bg-white px-4 py-2">
      <button
        onClick={() => !live && setOpen(!open)}
        className="flex w-full items-baseline gap-2 text-left text-sm text-gray-500"
      >
        {!live && <span className="text-gray-400">{open ? '▾' : '▸'}</span>}
        <span className="italic">
          {live
            ? `${step ? (STEPS[step] ?? step) : 'Thinking'}…`
            : `${step ? (STEPS[step] ?? step) : 'Thought this through'}${
                decision ? ` → ${decision}` : ''
              }`}
        </span>
        {when && <span className="ml-auto text-xs">{when}</span>}
      </button>
      {showing && (
        <p className="mt-1 whitespace-pre-wrap text-sm italic text-gray-600">
          {content}
        </p>
      )}
    </li>
  );
}

function ToolCall({
  event,
  when,
}: {
  event: Extract<TicketEvent, { eventType: 'tool_call' }>;
  when: string;
}) {
  const [open, setOpen] = useState(false);
  const outcome = event.cancelled
    ? { label: 'cancelled', tone: 'bg-gray-200 text-gray-700' }
    : event.error
      ? { label: 'failed', tone: 'bg-red-100 text-red-800' }
      : { label: 'ran', tone: 'bg-emerald-100 text-emerald-800' };

  // The customer is shown that something ran on their ticket, with the
  // arguments and the result stripped by the server. Nothing to unfold, so no
  // caret promising there is.
  const details =
    Object.keys(event.arguments ?? {}).length > 0 ||
    !!event.result ||
    !!event.error;

  return (
    <li className="ml-10 rounded-lg border border-l-4 border-amber-300 border-l-amber-400 bg-white px-4 py-3">
      <button
        onClick={() => details && setOpen(!open)}
        disabled={!details}
        className="flex w-full items-baseline gap-2 text-left"
      >
        {details && <span className="text-gray-400">{open ? '▾' : '▸'}</span>}
        <code className="text-sm font-medium">{event.tool}</code>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${outcome.tone}`}
        >
          {outcome.label}
        </span>
        <span className="ml-auto text-xs text-gray-500">{when}</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2 text-xs">
          <Block
            label="Arguments"
            body={JSON.stringify(event.arguments, null, 2)}
          />
          {event.result && <Block label="Result" body={event.result} />}
          {event.error && <Block label="Error" body={event.error} />}
        </div>
      )}
    </li>
  );
}

function Block({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <p className="font-semibold uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded bg-gray-50 p-2">
        {body}
      </pre>
    </div>
  );
}

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
