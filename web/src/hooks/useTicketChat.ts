/**
 * One ticket's live feed, as a topic on the shared hub socket.
 *
 * The message types and the topic pattern are generated from the backend's
 * AsyncAPI document by `pnpm gen:ws`, so `send` only accepts actions the
 * server declares and each handler's payload is narrowed by its action.
 */

import { useTopic } from '@chanx-js/client/react';
import { hub } from '@/generated';
import type { ToolProposalPayload } from '@/generated';
import type { TicketEvent } from '@/lib/types';

export type AgentStage = 'classified' | 'decided' | 'failed';

interface UseTicketChatOptions {
  ticketId: string;
  onNewEvent?: (event: TicketEvent) => void;
  onAgentProgress?: (stage: AgentStage, detail: string) => void;
  onApprovalRequired?: (draft: string, findings: string[]) => void;
  onToolProposal?: (proposal: ToolProposalPayload) => void;
  onTicketUpdated?: (status: string, priority: string) => void;
  onReasoning?: (step: string, delta: string) => void;
}

export function useTicketChat({
  ticketId,
  onNewEvent,
  onAgentProgress,
  onApprovalRequired,
  onToolProposal,
  onTicketUpdated,
  onReasoning,
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
        tool_proposal: (message) => onToolProposal?.(message.payload),
        reasoning_delta: (message) =>
          onReasoning?.(message.payload.step ?? '', message.payload.delta),
        ticket_updated: (message) =>
          onTicketUpdated?.(message.payload.status, message.payload.priority),
      },
    },
  );

  const sendMessage = (content: string, isPublic = false) => {
    send({ action: 'send_message', payload: { content, public: isPublic } });
  };

  const askAgent = (isPublic: boolean, question = '') => {
    send({ action: 'ask_agent', payload: { public: isPublic, question } });
  };

  const updateTicket = (fields: { status?: string; priority?: string }) => {
    send({
      action: 'update_ticket',
      payload: { status: fields.status ?? '', priority: fields.priority ?? '' },
    });
  };

  const setAgent = (on: boolean, message = '') => {
    send({ action: 'set_agent', payload: { on, message } });
  };

  const decideTool = (
    approved: boolean,
    toolArguments: Record<string, unknown>,
    publish: boolean,
  ) => {
    send({
      action: 'tool_decision',
      payload: { approved, arguments: toolArguments, publish },
    });
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
    updateTicket,
    decideTool,
    submitApproval,
    // `subscribed`, not socket status: the socket is shared, and a frame sent
    // before the server confirms this topic is dropped.
    isConnected: subscribed,
  };
}
