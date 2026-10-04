import type { TicketEvent } from '@/lib/types';

/**
 * One timeline from two sources: the page load and the live feed.
 *
 * Both can carry the same event. The socket subscribes before the fetch
 * resolves, so a row that arrives in that window is appended and then appears
 * again in the snapshot - and a snapshot taken a moment earlier would drop it
 * on a plain replace. Keyed by id, neither can happen.
 *
 * Order is the server's `createdAt`, and the sort is stable, so two events
 * recorded in the same second keep the order they arrived in.
 */
export function mergeEvents(
  current: TicketEvent[],
  incoming: TicketEvent[],
): TicketEvent[] {
  const byId = new Map(current.map((event) => [event.id, event]));
  for (const event of incoming) byId.set(event.id, event);
  return [...byId.values()].sort((a, b) =>
    a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : 0,
  );
}
