import { describe, expect, it } from 'vitest';
import { fillPlaceholders, placeholdersIn } from './placeholders';

describe('the placeholder contract', () => {
  it('matches the backend on what counts as one', () => {
    expect(placeholdersIn('Refunded {{amount}} to {{card}}.')).toEqual([
      'amount',
      'card',
    ]);
  });

  it('leaves a citation alone', () => {
    expect(placeholdersIn('Per [kb-003], refunds take 14 days.')).toEqual([]);
  });

  it('counts a repeat once', () => {
    expect(placeholdersIn('{{name}} and {{ name }}')).toEqual(['name']);
  });

  it('fills every mention', () => {
    expect(fillPlaceholders('{{a}} and {{ a }}', { a: '9' })).toBe('9 and 9');
  });

  it('refuses to fill from a blank box', () => {
    expect(fillPlaceholders('{{a}}', { a: '  ' })).toBe('{{a}}');
  });
});
