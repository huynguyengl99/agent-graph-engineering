import { useMemo, useState } from 'react';
import {
  AutoForm,
  AutoFormSubmit,
  type FieldConfig,
} from '@/components/auto-form';
import { isFreeText, zodFromJsonSchema } from '@/lib/zodFromJsonSchema';
import { corrections, decisionArguments } from '@/lib/toolForm';
import type { ToolApprovalPayload } from '@/generated';

interface Props {
  proposal: ToolApprovalPayload;
  onDecide: (approved: boolean, args: Record<string, unknown>) => void;
  disabled?: boolean;
}

/**
 * The tool gate. Every input is generated from the schema the agent sent, so a
 * tool added to the agent is reviewable here without touching this file.
 *
 * Nothing has run at this point: the graph is parked in the agent's
 * checkpointer, and it stays parked until this card is answered.
 */
export function ToolApprovalCard({ proposal, onDecide, disabled }: Props) {
  const schema = useMemo(
    () => zodFromJsonSchema(proposal.argumentsSchema),
    [proposal.argumentsSchema],
  );

  // Which arguments read as prose. The same schema drives the field type, so
  // this is a presentation note, not a second description of the arguments.
  const fieldConfig = useMemo(() => {
    const config: Record<string, { fieldType: 'textarea' }> = {};
    for (const [name, field] of Object.entries(schema.shape)) {
      if (isFreeText(name, field.description)) {
        config[name] = { fieldType: 'textarea' };
      }
    }
    return config as FieldConfig<Record<string, unknown>>;
  }, [schema]);

  const proposed = (proposal.arguments ?? {}) as Record<string, unknown>;
  const [values, setValues] = useState<Record<string, unknown>>(proposed);

  const changed = corrections(schema, values, proposed);
  const edited = Object.keys(changed).length > 0;
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

      <AutoForm
        schema={schema}
        values={proposed}
        fieldConfig={fieldConfig}
        disabled={disabled}
        className="mt-3 space-y-3"
        onValuesChange={setValues}
        // Validation is the schema's, so approval is only reachable once the
        // arguments would actually satisfy the tool.
        onSubmit={(submitted) =>
          onDecide(
            true,
            decisionArguments(
              schema,
              submitted as Record<string, unknown>,
              proposed,
            ),
          )
        }
      >
        {Object.keys(schema.shape).length === 0 && (
          <p className="text-xs text-amber-800">
            This tool takes no arguments.
          </p>
        )}

        <div className="mt-4 flex items-center gap-2">
          <AutoFormSubmit
            disabled={disabled}
            className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-40"
          >
            {edited ? 'Run with my corrections' : 'Approve and run'}
          </AutoFormSubmit>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onDecide(false, {})}
            className="rounded border border-amber-400 px-4 py-2 text-sm text-amber-900 hover:bg-amber-100 disabled:opacity-40"
          >
            Cancel
          </button>
          {edited && (
            <span className="text-xs text-amber-800">
              {Object.keys(changed).length} field
              {Object.keys(changed).length === 1 ? '' : 's'} changed
            </span>
          )}
        </div>
      </AutoForm>
    </section>
  );
}
