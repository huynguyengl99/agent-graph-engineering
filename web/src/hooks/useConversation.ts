/**
 * One conversation with the assistant, as a topic on the shared hub socket.
 *
 * The answer arrives as deltas while it is produced and then once more in
 * full, so the streaming text is held separately and cleared when the final
 * message lands. Without that the answer would appear twice.
 *
 * A turn can also end without an answer: if the assistant wants to run a tool
 * that needs clearing, the graph parks and `tool_approval` arrives instead.
 * That proposal is held until someone answers it, because there is nothing
 * else coming until they do.
 */

import { useCallback, useState } from 'react';
import { useTopic } from '@chanx-js/client/react';
import { hub } from '@/generated';
import type { ToolApprovalPayload } from '@/generated';
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
  const [pendingTool, setPendingTool] = useState<ToolApprovalPayload | null>(
    null,
  );

  const handleMessage = useCallback(
    (message: ChatMessage) => {
      setStreaming('');
      // A turn that ends in a message has moved past the gate, one way or
      // another. A card left standing here could be answered twice.
      setPendingTool(null);
      onMessage?.(message);
    },
    [onMessage],
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
        tool_approval: (frame) => {
          setStreaming('');
          setPendingTool(frame.payload);
        },
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
    },
  );

  const ask = (content: string) => {
    send({ action: 'ask', payload: { content } });
  };

  const decideTool = (approved: boolean, args: Record<string, unknown>) => {
    // Cleared before the answer arrives: the card is a question that has now
    // been answered, and leaving it up invites a second click on a run that
    // has already resumed.
    setPendingTool(null);
    send({ action: 'tool_decision', payload: { approved, arguments: args } });
  };

  const sendToTicket = (ticketId: string, content: string) => {
    send({
      action: 'draft_to_ticket',
      payload: { ticketId, content },
    });
  };

  return {
    ask,
    sendToTicket,
    decideTool,
    pendingTool,
    streaming,
    isReady: subscribed,
  };
}
