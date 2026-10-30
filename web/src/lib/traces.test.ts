import { describe, expect, it } from 'vitest';

import { conversationsOf, type RunSummary } from '@/lib/traces';

function run(runId: string, thread: string): RunSummary {
  return {
    run_id: runId,
    label: '',
    thread,
    started_at: null,
    duration_ms: 0,
    spans: 1,
    calls: 1,
    cost_usd: 0.01,
    priced: true,
  };
}

describe('conversationsOf', () => {
  it('puts the turns of one thread together', () => {
    const grouped = conversationsOf([
      run('c', 'support:customer:t-9'),
      run('b', 'support:team:t-9'),
      run('a', 'support:customer:t-9'),
    ]);

    expect(grouped.map((found) => [found.thread, found.runs.length])).toEqual([
      ['support:customer:t-9', 2],
      ['support:team:t-9', 1],
    ]);
  });

  it('reads a conversation in the order it happened', () => {
    const newestFirst = [
      run('third', 't'),
      run('second', 't'),
      run('first', 't'),
    ];

    const [conversation] = conversationsOf(newestFirst);

    expect(conversation.runs.map((found) => found.run_id)).toEqual([
      'first',
      'second',
      'third',
    ]);
  });

  it('keeps a run whose thread went unrecorded', () => {
    const [conversation] = conversationsOf([run('orphan', '')]);

    expect(conversation.thread).toBe('orphan');
    expect(conversation.runs).toHaveLength(1);
  });
});
