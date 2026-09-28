// @vitest-environment happy-dom
import { act, cleanup, renderHook } from '@testing-library/react';
import { setDefaultClient } from '@chanx-js/client/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTicketChat } from './useTicketChat';
import { FakeSocket, fakeSocketFactory } from '@/test/fake-socket';

const TICKET = '11111111-2222-3333-4444-555555555555';

beforeEach(() => {
  FakeSocket.reset();
  setDefaultClient({
    baseUrl: 'ws://test.local',
    socketFactory: fakeSocketFactory,
    closeDelay: 0,
    heartbeat: false,
    reconnectInterval: 5,
  });
});

afterEach(cleanup);

type Handlers = Omit<Parameters<typeof useTicketChat>[0], 'ticketId'>;

function mount(handlers: Handlers = {}) {
  return renderHook(() => useTicketChat({ ticketId: TICKET, ...handlers }));
}

describe('useTicketChat', () => {
  it('connects to the address the generated descriptor declares', async () => {
    mount();
    // The {ticket_id} parameter comes from the AsyncAPI address, not from a
    // string built by hand in the hook.
    expect(FakeSocket.last.url).toBe(`ws://test.local/ws/tickets/${TICKET}/`);
  });

  it('reports the connection status', async () => {
    const { result } = mount();
    expect(result.current.isConnected).toBe(false);

    await act(async () => FakeSocket.last.accept());
    expect(result.current.isConnected).toBe(true);
  });

  it('sends a comment as a send_message frame', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.accept());

    await act(async () => result.current.sendMessage('Still broken.'));

    expect(FakeSocket.last.lastSent).toMatchObject({
      action: 'send_message',
      payload: { content: 'Still broken.' },
    });
  });

  it('routes new_event to the event handler', async () => {
    const onNewEvent = vi.fn();
    mount({ onNewEvent });
    await act(async () => FakeSocket.last.accept());

    const event = { id: 1, eventType: 'comment', content: 'hi' };
    await act(async () =>
      FakeSocket.last.receive({ action: 'new_event', payload: { event } })
    );

    expect(onNewEvent).toHaveBeenCalledWith(event);
  });

  it('routes agent_progress with its stage and detail', async () => {
    const onAgentProgress = vi.fn();
    mount({ onAgentProgress });
    await act(async () => FakeSocket.last.accept());

    await act(async () =>
      FakeSocket.last.receive({
        action: 'agent_progress',
        payload: { stage: 'classified', detail: 'billing / medium' },
      })
    );

    expect(onAgentProgress).toHaveBeenCalledWith('classified', 'billing / medium');
  });

  it('surfaces the draft when the graph parks for approval', async () => {
    const onApprovalRequired = vi.fn();
    mount({ onApprovalRequired });
    await act(async () => FakeSocket.last.accept());

    await act(async () =>
      FakeSocket.last.receive({
        action: 'approval_required',
        payload: { draft: 'Proration explains the second charge.' },
      })
    );

    expect(onApprovalRequired).toHaveBeenCalledWith(
      'Proration explains the second charge.'
    );
  });

  it('sends an approval decision, and an edit when the draft changed', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.accept());

    await act(async () => result.current.submitApproval(true));
    expect(FakeSocket.last.lastSent).toMatchObject({
      action: 'approval_decision',
      payload: { approved: true, content: null },
    });

    await act(async () => result.current.submitApproval(true, 'Rewritten.'));
    expect(FakeSocket.last.lastSent).toMatchObject({
      action: 'approval_decision',
      payload: { approved: true, content: 'Rewritten.' },
    });
  });

  it('rejection is sent as approved: false', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.accept());

    await act(async () => result.current.submitApproval(false));

    expect(FakeSocket.last.lastSent).toMatchObject({
      action: 'approval_decision',
      payload: { approved: false },
    });
  });

  it('ignores frames it has no handler for', async () => {
    const onNewEvent = vi.fn();
    mount({ onNewEvent });
    await act(async () => FakeSocket.last.accept());

    await act(async () =>
      FakeSocket.last.receive({ action: 'streaming', payload: { chunk: 'x' } })
    );

    expect(onNewEvent).not.toHaveBeenCalled();
  });
});
