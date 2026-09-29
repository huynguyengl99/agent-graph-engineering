import type { ChatMessage } from '@/lib/types';

const TONES = {
  user: 'bg-white border-gray-200',
  assistant: 'bg-indigo-50 border-indigo-200',
} as const;

export function ChatMessageItem({
  message,
  pending = false,
}: {
  message: ChatMessage;
  pending?: boolean;
}) {
  const role = message.role === 'assistant' ? 'assistant' : 'user';
  return (
    <li className={`rounded-lg border px-4 py-3 ${TONES[role]}`}>
      <div className="flex items-baseline justify-between gap-4">
        <span className="font-medium">
          {role === 'assistant' ? 'Assistant' : 'You'}
        </span>
        {pending && (
          <span className="text-xs text-indigo-500">answering…</span>
        )}
      </div>
      <p className="mt-1 whitespace-pre-wrap">{message.content}</p>
    </li>
  );
}
