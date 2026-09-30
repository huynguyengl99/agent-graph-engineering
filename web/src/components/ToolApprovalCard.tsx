import { useMemo, useState } from 'react';
import {
  corrections,
  decisionArguments,
  fieldsFromSchema,
  incomplete,
  initialValues,
  type ToolField,
} from '@/lib/toolForm';
import type { ToolApprovalPayload } from '@/generated';

interface Props {
  proposal: ToolApprovalPayload;
  onDecide: (approved: boolean, args: Record<string, unknown>) => void;
  disabled?: boolean;
}

function Field({
  field,
  value,
  onChange,
  changed,
}: {
  field: ToolField;
  value: string;
  onChange: (value: string) => void;
  changed: boolean;
}) {
  const border = changed
    ? 'border-indigo-400 bg-indigo-50'
    : 'border-amber-300';
  const shared = `w-full rounded border px-3 py-2 text-sm ${border}`;

  return (
    <label className="block">
      <span className="flex items-center gap-2 text-xs font-medium text-amber-900">
        {field.label}
        {field.required && <span className="text-amber-700">required</span>}
        {changed && (
          <span className="rounded bg-indigo-100 px-1.5 text-indigo-800">
            corrected
          </span>
        )}
      </span>
      {field.description && (
        <span className="mt-0.5 block text-xs text-amber-800">
          {field.description}
        </span>
      )}

      {field.kind === 'text' ? (
        <textarea
          aria-label={field.label}
          value={value}
          rows={3}
          onChange={(e) => onChange(e.target.value)}
          className={`mt-1 ${shared}`}
        />
      ) : field.kind === 'enum' ? (
        <select
          aria-label={field.label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`mt-1 ${shared}`}
        >
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : field.kind === 'boolean' ? (
        <select
          aria-label={field.label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`mt-1 ${shared}`}
        >
          <option value="true">yes</option>
          <option value="false">no</option>
        </select>
      ) : (
        <input
          aria-label={field.label}
          type={field.kind === 'string' ? 'text' : 'number'}
          step={field.kind === 'number' ? 'any' : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`mt-1 ${shared}`}
        />
      )}
    </label>
  );
}

/**
 * The tool gate. Every input here is generated from the schema the agent sent,
 * so a tool added to the agent is reviewable without touching this file.
 *
 * Nothing has run at this point. The graph is parked in the agent's
 * checkpointer, and it stays parked until this card is answered.
 */
export function ToolApprovalCard({ proposal, onDecide, disabled }: Props) {
  const fields = useMemo(
    () => fieldsFromSchema(proposal.argumentsSchema),
    [proposal.argumentsSchema],
  );
  const [values, setValues] = useState(() =>
    initialValues(fields, proposal.arguments),
  );

  const changed = corrections(fields, values, proposal.arguments);
  const edited = Object.keys(changed).length > 0;
  // A required field left empty is usually the planner having misnamed it. The
  // tool would refuse the call anyway; refusing here says why.
  const blank = incomplete(fields, values);
  const dropped = proposal.unknownArguments ?? [];

  return (
    <section className="rounded-lg border-2 border-amber-300 bg-amber-50 p-4">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold text-amber-900">
          Run <code className="text-amber-950">{proposal.tool}</code>?
        </h3>
        <span className="rounded bg-amber-200 px-2 py-0.5 text-xs text-amber-900">
          nothing has run yet
        </span>
      </div>
      {proposal.description && (
        <p className="mt-2 text-sm text-amber-900">{proposal.description}</p>
      )}

      {dropped.length > 0 && (
        <p className="mt-2 text-xs text-amber-800">
          The assistant also passed {dropped.join(', ')}, which this tool does
          not take. Dropped, so check the fields below.
        </p>
      )}

      <div className="mt-3 space-y-3">
        {fields.map((field) => (
          <Field
            key={field.name}
            field={field}
            value={values[field.name] ?? ''}
            changed={field.name in changed}
            onChange={(value) =>
              setValues((current) => ({ ...current, [field.name]: value }))
            }
          />
        ))}
        {fields.length === 0 && (
          <p className="text-xs text-amber-800">
            This tool takes no arguments.
          </p>
        )}
      </div>

      <div className="mt-4 flex items-center gap-2">
        <button
          disabled={disabled || blank.length > 0}
          onClick={() =>
            onDecide(
              true,
              decisionArguments(fields, values, proposal.arguments),
            )
          }
          className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-40"
        >
          {edited ? 'Run with my corrections' : 'Approve and run'}
        </button>
        <button
          disabled={disabled}
          onClick={() => onDecide(false, {})}
          className="rounded border border-amber-400 px-4 py-2 text-sm text-amber-900 hover:bg-amber-100 disabled:opacity-40"
        >
          Cancel
        </button>
        {blank.length > 0 ? (
          <span className="text-xs text-amber-800">
            {blank.join(', ')} {blank.length === 1 ? 'is' : 'are'} required
          </span>
        ) : (
          edited && (
            <span className="text-xs text-amber-800">
              {Object.keys(changed).length} field
              {Object.keys(changed).length === 1 ? '' : 's'} changed
            </span>
          )
        )}
      </div>
    </section>
  );
}
