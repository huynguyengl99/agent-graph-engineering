/**
 * Where a ticket stands, for the list beside the one being read.
 *
 * The list is loaded once and the detail is subscribed to a topic, so without
 * this the row keeps saying `NEEDS A PERSON` while the header beside it says
 * the assistant has it back. Subscribing the list to every ticket's topic would
 * cost one subscription per row to deliver the same three fields.
 */

import type { Ticket } from '@/lib/types';

export type TicketPatch = Partial<
  Pick<Ticket, 'status' | 'priority' | 'handling'>
> & {
  id: string;
};

const listeners = new Set<(patch: TicketPatch) => void>();

export function publishTicketChange(patch: TicketPatch): void {
  for (const listener of listeners) listener(patch);
}

export function onTicketChange(
  listener: (patch: TicketPatch) => void,
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
