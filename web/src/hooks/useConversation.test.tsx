// @vitest-environment happy-dom
/**
 * The gate as the browser sees it: a turn that ends in a question instead of
 * an answer, and a decision that goes back on the same topic.
 */
import { act, cleanup, renderHook } from '@testing-library/react';
import { setDefaultClient } from '@chanx-js/client/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useConversation } from './useConversation';
import { FakeSocket, fakeSocketFactory } from '@/test/fake-socket';

const CONVERSATION = '99999999-8888-7777-6666-555555555555';
const TOPIC = `conversation:${CONVERSATION}`;

const PROPOSAL = {
  tool: 'issue_refund',
  description: 'Refund a charge.',
  arguments: { email: 'demo@example.com', amount: 29.0 },
  argumentsSchema: {
    type: 'object',
    required: ['email', 'amount'],
    properties: {
      email: { type: 'string', description: 'Who to refund.' },
      amount: { type: 'number', description: 'In pounds.' },
    },
  },
};

let base = '';
let run = 0;

beforeEach(() => {
  FakeSocket.reset();
  base = `ws://conv-${run++}.local`;
  setDefaultClient({
    baseUrl: base,
    socketFactory: fakeSocketFactory,
    closeDelay: 0,
    heartbeat: false,
    reconnectInterval: 5,
  });
});

afterEach(() => {
  cleanup();
  FakeSocket.closeAll();
});

function mount() {
  return renderHook(() => useConversation({ conversationId: CONVERSATION }));
}

async function park() {
  await act(async () =>
    FakeSocket.last.receive({
      topic: TOPIC,
      action: 'tool_approval',
      payload: PROPOSAL,
    }),
  );
}

describe('useConversation', () => {
  it('takes a persisted turn as it arrives, without rebuilding it', async () => {
    const seen: unknown[] = [];
    const { result } = renderHook(() =>
      useConversation({
        conversationId: CONVERSATION,
        onMessage: (m) => seen.push(m),
      }),
    );
    await act(async () => FakeSocket.last.acceptAndSubscribe());

    const message = {
      id: 'm-1',
      role: 'assistant',
      content: 'Here you go.',
      createdAt: '2026-09-30T10:00:00Z',
    };
    await act(async () =>
      FakeSocket.last.receive({
        topic: TOPIC,
        action: 'assistant_done',
        payload: { message },
      }),
    );

    // Including createdAt: the client used to invent one here, so a persisted
    // turn and the same turn after a reload had different timestamps.
    expect(seen).toEqual([message]);
    expect(result.current.streaming).toBe('');
  });
});

describe('useConversation at the tool gate', () => {
  it('holds the proposal, because nothing else is coming until it is answered', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.acceptAndSubscribe());

    await park();

    expect(result.current.pendingTool?.tool).toBe('issue_refund');
    expect(result.current.pendingTool?.arguments).toEqual({
      email: 'demo@example.com',
      amount: 29.0,
    });
  });

  it('drops a half-streamed answer when the run parks instead', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.acceptAndSubscribe());
    await act(async () =>
      FakeSocket.last.receive({
        topic: TOPIC,
        action: 'token',
        payload: { delta: 'Let me ' },
      }),
    );

    await park();

    expect(result.current.streaming).toBe('');
  });

  it('sends an approval as the proposal stands', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.acceptAndSubscribe());
    await park();

    await act(async () => result.current.decideTool(true, {}));

    expect(FakeSocket.last.lastSent).toMatchObject({
      action: 'tool_decision',
      payload: { approved: true, arguments: {} },
    });
  });

  it('sends corrected arguments as the arguments to run', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.acceptAndSubscribe());
    await park();

    await act(async () =>
      result.current.decideTool(true, {
        email: 'demo@example.com',
        amount: 9,
      }),
    );

    expect(FakeSocket.last.lastSent).toMatchObject({
      action: 'tool_decision',
      payload: { approved: true, arguments: { amount: 9 } },
    });
  });

  it('clears the card on a decision, so it cannot be answered twice', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.acceptAndSubscribe());
    await park();

    await act(async () => result.current.decideTool(false, {}));

    expect(result.current.pendingTool).toBeNull();
  });

  it('clears the card when the turn ends some other way', async () => {
    const { result } = mount();
    await act(async () => FakeSocket.last.acceptAndSubscribe());
    await park();

    await act(async () =>
      FakeSocket.last.receive({
        topic: TOPIC,
        action: 'chat_error',
        payload: { detail: 'The assistant is unavailable.' },
      }),
    );

    expect(result.current.pendingTool).toBeNull();
  });
});
