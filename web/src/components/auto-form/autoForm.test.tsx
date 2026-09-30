// @vitest-environment happy-dom
/**
 * One form engine, two sources of schema.
 *
 * These tests use a generated REST schema and a hand-written one, and never a
 * tool: the point of AutoForm is that it knows nothing about what it renders.
 */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

import { schemas } from '@/schemas/backend';
import { AutoForm, AutoFormSubmit } from './index';

afterEach(cleanup);

const submit = () => screen.getByRole('button') as HTMLButtonElement;

describe('AutoForm', () => {
  it('renders a field per schema key, with the type the schema declares', () => {
    render(
      <AutoForm
        schema={z.object({
          name: z.string(),
          count: z.number(),
          active: z.boolean(),
          size: z.enum(['small', 'large']),
        })}
        onSubmit={vi.fn()}
      />,
    );

    expect((screen.getByLabelText('Name') as HTMLInputElement).type).toBe(
      'text',
    );
    expect((screen.getByLabelText('Count') as HTMLInputElement).type).toBe(
      'number',
    );
    expect((screen.getByLabelText('Active') as HTMLInputElement).type).toBe(
      'checkbox',
    );
    expect(screen.getByLabelText('Size').tagName).toBe('SELECT');
  });

  it('offers an enum’s own options', () => {
    render(
      <AutoForm
        schema={z.object({ size: z.enum(['small', 'large']) })}
        onSubmit={vi.fn()}
      />,
    );

    const options = Array.from(
      (screen.getByLabelText('Size') as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(options).toEqual(['small', 'large']);
  });

  it('labels a field without anyone writing the copy', () => {
    render(
      <AutoForm
        schema={z.object({
          amount_in_pence: z.number(),
          createdAt: z.string(),
        })}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Amount in pence')).toBeTruthy();
    expect(screen.getByLabelText('Created At')).toBeTruthy();
  });

  it('shows a described field’s description as help', () => {
    render(
      <AutoForm
        schema={z.object({ email: z.string().describe('Who to refund.') })}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText('Who to refund.')).toBeTruthy();
  });

  it('starts from the values it is given', () => {
    render(
      <AutoForm
        schema={z.object({ name: z.string() })}
        values={{ name: 'Ada' }}
        onSubmit={vi.fn()}
      />,
    );

    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe(
      'Ada',
    );
  });

  it('starts from a schema default when no value is given', () => {
    render(
      <AutoForm
        schema={z.object({ tries: z.number().default(3) })}
        onSubmit={vi.fn()}
      />,
    );

    expect((screen.getByLabelText('Tries') as HTMLInputElement).value).toBe(
      '3',
    );
  });

  it('submits values parsed to their schema types', async () => {
    const onSubmit = vi.fn();
    render(
      <AutoForm
        schema={z.object({ name: z.string(), count: z.number() })}
        values={{ name: 'Ada', count: 1 }}
        onSubmit={onSubmit}
      >
        <AutoFormSubmit />
      </AutoForm>,
    );

    fireEvent.change(screen.getByLabelText('Count'), {
      target: { value: '7' },
    });
    await waitFor(() => expect(submit().disabled).toBe(false));
    fireEvent.click(submit());

    // A number, not "7": the form and the request agree because the schema is
    // the same object.
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ name: 'Ada', count: 7 }),
    );
  });

  it('will not submit values the schema rejects', async () => {
    const onSubmit = vi.fn();
    render(
      <AutoForm
        schema={z.object({ name: z.string().min(2) })}
        onSubmit={onSubmit}
      >
        <AutoFormSubmit />
      </AutoForm>,
    );

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'a' } });

    await waitFor(() => expect(submit().disabled).toBe(true));
    fireEvent.click(submit());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('puts a server-side field error on its own field', () => {
    render(
      <AutoForm
        schema={z.object({ title: z.string() })}
        apiErrors={[{ field: 'title', error: 'That title is taken.' }]}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText('That title is taken.')).toBeTruthy();
  });

  it('leaves out a field the caller sets itself', () => {
    render(
      <AutoForm
        schema={z.object({ title: z.string(), owner: z.string() })}
        hiddenFields={['owner']}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Title')).toBeTruthy();
    expect(screen.queryByLabelText('Owner')).toBeNull();
  });

  it('honours a field type override', () => {
    render(
      <AutoForm
        schema={z.object({ body: z.string() })}
        fieldConfig={{ body: { fieldType: 'textarea' } }}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Body').tagName).toBe('TEXTAREA');
  });

  it('renders a generated REST schema with nothing written by hand', () => {
    // The whole claim, in one test: this schema came out of the OpenAPI
    // generator, and the form for it is three lines of JSX.
    render(
      <AutoForm schema={schemas.TicketCreateRequest} onSubmit={vi.fn()} />,
    );

    expect(screen.getByLabelText('Title')).toBeTruthy();
    expect(screen.getByLabelText('Description')).toBeTruthy();
    // `priority` is an optional enum on the server, so it is a select here.
    expect(screen.getByLabelText('Priority').tagName).toBe('SELECT');
  });
});
