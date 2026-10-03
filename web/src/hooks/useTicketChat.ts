/**
 * One ticket's live feed, as a topic on the shared hub socket.
 *
 * The message types and the topic pattern are generated from the backend's
 * AsyncAPI document by `pnpm gen:ws`, so `send` only accepts actions the
 * server declares and each handler's payload is narrowed by its action.
 */

import { useTopic } from '@chanx-js/client/react';
import { hub } from '@/generated';
import type { TicketEvent } from '@/lib/types';

export type AgentStage = 'classified' | 'decided' | 'failed';

interface UseTicketChatOptions {
  ticketId: string;
  onNewEvent?: (event: TicketEvent) => void;
  onAgentProgress?: (stage: AgentStage, detail: string) => void;
  onApprovalRequired?: (draft: string, findings: string[]) => void;
}

export function useTicketChat({
  ticketId,
  onNewEvent,
  onAgentProgress,
  onApprovalRequired,
}: UseTicketChatOptions) {
  const { send, subscribed } = useTopic(
    hub,
    hub.topics.ticketTopic.with({ ticket_id: ticketId }),
    {
      // Handlers rather than a lastMessage switch: no frame is dropped between
      // renders, and changing a handler does not rejoin the topic.
      on: {
        new_event: (message) => onNewEvent?.(message.payload.event),
        agent_progress: (message) =>
          onAgentProgress?.(message.payload.stage, message.payload.detail),
        approval_required: (message) =>
          onApprovalRequired?.(
            message.payload.draft,
            message.payload.findings ?? [],
          ),
      },
    },
  );

  const sendMessage = (content: string, isPublic = false) => {
    send({ action: 'send_message', payload: { content, public: isPublic } });
  };

  const askAgent = (isPublic: boolean, question = '') => {
    send({ action: 'ask_agent', payload: { public: isPublic, question } });
  };

  const setAgent = (on: boolean, reason = '') => {
    send({ action: 'set_agent', payload: { on, reason } });
  };

  const submitApproval = (approved: boolean, content?: string) => {
    send({
      action: 'approval_decision',
      payload: { approved, content: content ?? null },
    });
  };

  return {
    sendMessage,
    askAgent,
    setAgent,
    submitApproval,
    // `subscribed`, not socket status: the socket is shared, and a frame sent
    // before the server confirms this topic is dropped.
    isConnected: subscribed,
  };
}
