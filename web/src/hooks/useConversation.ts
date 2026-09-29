/**
 * One conversation with the assistant, as a topic on the shared hub socket.
 *
 * The answer arrives as deltas while it is produced and then once more in
 * full, so the streaming text is held separately and cleared when the final
 * message lands. Without that the answer would appear twice.
 */

import { useCallback, useState } from 'react';
import { useTopic } from '@chanx-js/client/react';
import { hub } from '@/generated';
import type { ChatMessage } from '@/lib/types';

interface UseConversationOptions {
  conversationId: string;
  onMessage?: (message: ChatMessage) => void;
}

export function useConversation({
  conversationId,
  onMessage,
}: UseConversationOptions) {
  const [streaming, setStreaming] = useState('');

  const handleMessage = useCallback(
    (message: ChatMessage) => {
      setStreaming('');
      onMessage?.(message);
    },
    [onMessage]
  );

  const { send, subscribed } = useTopic(
    hub,
    hub.topics.conversationTopic.with({ conversation_id: conversationId }),
    {
      on: {
        chat_message: (frame) =>
          handleMessage({
            id: frame.payload.id,
            role: frame.payload.role,
            content: frame.payload.content,
            createdAt: frame.payload.createdAt,
          }),
        token: (frame) => setStreaming((text) => text + frame.payload.delta),
        assistant_done: (frame) =>
          handleMessage({
            id: frame.payload.messageId,
            role: 'assistant',
            content: frame.payload.content,
            createdAt: new Date().toISOString(),
          }),
        chat_error: (frame) => {
          setStreaming('');
          handleMessage({
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: frame.payload.detail,
            createdAt: new Date().toISOString(),
          });
        },
      },
    }
  );

  const ask = (content: string) => {
    send({ action: 'ask', payload: { content } });
  };

  const sendToTicket = (ticketId: string, content: string) => {
    send({
      action: 'draft_to_ticket',
      payload: { ticketId, content },
    });
  };

  return { ask, sendToTicket, streaming, isReady: subscribed };
}
