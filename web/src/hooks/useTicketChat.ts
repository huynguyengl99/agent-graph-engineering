/**
 * Live ticket channel: post comments, watch the triage agent work.
 *
 * The message types and the channel descriptor are generated from the backend's
 * AsyncAPI document by `pnpm gen:ws`, so `send` only accepts actions the server
 * declares and each handler's payload is narrowed by its action.
 */

import { useChannel } from '@chanx-js/client/react';
import { tickets } from '@/generated';
import type { TicketEvent } from '@/lib/types';

export type AgentStage = 'classified' | 'decided' | 'failed';

interface UseTicketChatOptions {
  ticketId: string;
  onNewEvent?: (event: TicketEvent) => void;
  onAgentProgress?: (stage: AgentStage, detail: string) => void;
  onApprovalRequired?: (draft: string) => void;
}

export function useTicketChat({
  ticketId,
  onNewEvent,
  onAgentProgress,
  onApprovalRequired,
}: UseTicketChatOptions) {
  const { send, status } = useChannel(tickets, {
    params: { ticket_id: ticketId },
    // Handlers rather than a lastMessage switch: no frame is dropped between
    // renders, and changing a handler does not reconnect the socket.
    on: {
      new_event: (message) => onNewEvent?.(message.payload.event),
      complete_streaming: (message) => onNewEvent?.(message.payload.event),
      agent_progress: (message) =>
        onAgentProgress?.(message.payload.stage, message.payload.detail),
      approval_required: (message) => onApprovalRequired?.(message.payload.draft),
    },
  });

  const sendMessage = (content: string) => {
    send({ action: 'send_message', payload: { content } });
  };

  const submitApproval = (approved: boolean, content?: string) => {
    send({ action: 'approval_decision', payload: { approved, content: content ?? null } });
  };

  return {
    sendMessage,
    submitApproval,
    isConnected: status === 'open',
  };
}
