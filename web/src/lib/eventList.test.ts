/**
 * The timeline is built from a page load and a live feed at once.
 *
 * Appending whatever arrived and replacing on load is wrong in both
 * directions: the socket subscribes before the fetch resolves, so an event in
 * that window rendered twice, and a snapshot taken a moment earlier dropped it.
 */
import { describe, expect, it } from 'vitest';
import { mergeEvents } from '@/lib/eventList';
import type { TicketEvent } from '@/lib/types';

const event = (id: number, createdAt: string, content = ''): TicketEvent =>
  ({
    id,
    eventType: 'comment',
    createdAt,
    visibility: 'public',
    createdBy: null,
    content,
  }) as unknown as TicketEvent;

describe('mergeEvents', () => {
  it('keeps one row when both sources carry the event', () => {
    const live = event(1, '2026-10-05T10:00:00Z');

    const merged = mergeEvents([live], [event(1, '2026-10-05T10:00:00Z')]);

    expect(merged).toHaveLength(1);
  });

  it('keeps a live event the snapshot was taken before', () => {
    const live = event(2, '2026-10-05T10:00:01Z');

    const merged = mergeEvents([live], [event(1, '2026-10-05T10:00:00Z')]);

    expect(merged.map((e) => e.id)).toEqual([1, 2]);
  });

  it('orders by when the server recorded it, not when it arrived', () => {
    const merged = mergeEvents(
      [event(3, '2026-10-05T10:00:02Z')],
      [event(1, '2026-10-05T10:00:00Z'), event(2, '2026-10-05T10:00:01Z')],
    );

    expect(merged.map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it('prefers the newer copy of a row that changed', () => {
    const merged = mergeEvents(
      [event(1, '2026-10-05T10:00:00Z', 'stale')],
      [event(1, '2026-10-05T10:00:00Z', 'fresh')],
    );

    expect(merged).toHaveLength(1);
    expect((merged[0] as { content: string }).content).toBe('fresh');
  });

  it('leaves two events recorded in the same second as they arrived', () => {
    const merged = mergeEvents(
      [event(1, '2026-10-05T10:00:00Z'), event(2, '2026-10-05T10:00:00Z')],
      [],
    );

    expect(merged.map((e) => e.id)).toEqual([1, 2]);
  });
});
