import { describe, expect, it } from 'vitest';
import { errorBody, fieldErrors } from './apiErrors';

describe('fieldErrors', () => {
  it('reads the shape drf-standardized-errors actually sends', () => {
    // Parsing DRF's plain shape found nothing here, so the server said exactly
    // what was wrong and the form showed a generic failure.
    const body = {
      type: 'validation_error',
      errors: [
        { code: 'invalid', detail: 'Use provider:name.', attr: 'model' },
        {
          code: 'blank',
          detail: 'This field may not be blank.',
          attr: 'title',
        },
      ],
    };

    expect(fieldErrors(body)).toEqual([
      { field: 'model', error: 'Use provider:name.' },
      { field: 'title', error: 'This field may not be blank.' },
    ]);
  });

  it('still reads the plain DRF shape', () => {
    expect(fieldErrors({ model: ['Use provider:name.'] })).toEqual([
      { field: 'model', error: 'Use provider:name.' },
    ]);
  });

  it('ignores an entry with nothing to attach to a field', () => {
    const body = { errors: [{ code: 'throttled', detail: 'Slow down.' }] };

    expect(fieldErrors(body)).toEqual([]);
  });

  it('is empty for anything that is not an error body', () => {
    expect(fieldErrors(undefined)).toEqual([]);
    expect(fieldErrors('nope')).toEqual([]);
    expect(fieldErrors({})).toEqual([]);
  });
});

describe('errorBody', () => {
  it('digs the body out of an axios error', () => {
    expect(errorBody({ response: { data: { errors: [] } } })).toEqual({
      errors: [],
    });
  });

  it('is undefined when the request never got a response', () => {
    expect(errorBody(new Error('network'))).toBeUndefined();
  });
});
