/**
 * Live ticket channel: post comments, watch the triage agent work.
 */

import { useCallback, useEffect, useRef } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import type { TicketEvent } from '@/lib/types';

export type AgentStage = 'classified' | 'decided' | 'failed';

/**
 * Mirrors the `tickets` channel in the backend's AsyncAPI document. The
 * contract track replaces this hand-written union with a generated one.
 */
type IncomingMessage =
  | { action: 'new_event'; payload: { event: TicketEvent } }
  | { action: 'agent_progress'; payload: { stage: AgentStage; detail: string } }
  | { action: 'approval_required'; payload: { draft: string } }
  | { action: 'streaming'; payload: { chunk: string } }
  | { action: 'complete_streaming'; payload: { event: TicketEvent } }
  | { action: 'pong'; payload: null }
  | { action: 'complete'; payload: null }
  | { action: 'group_complete'; payload: null };

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
  const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${
    location.host
  }/ws/tickets/${ticketId}/`;

  const { sendJsonMessage, lastJsonMessage, readyState } = useWebSocket(wsUrl, {
    share: false,
    shouldReconnect: () => true,
  });

  // Hold callbacks in a ref so the delivery effect depends only on the
  // message. Without this, a parent re-render with new closures would re-run
  // the effect and replay the last message.
  const handlers = useRef({ onNewEvent, onAgentProgress, onApprovalRequired });
  useEffect(() => {
    handlers.current = { onNewEvent, onAgentProgress, onApprovalRequired };
  }, [onNewEvent, onAgentProgress, onApprovalRequired]);

  useEffect(() => {
    if (!lastJsonMessage) return;
    const message = lastJsonMessage as IncomingMessage;

    switch (message.action) {
      case 'new_event':
      case 'complete_streaming':
        handlers.current.onNewEvent?.(message.payload.event);
        break;
      case 'agent_progress':
        handlers.current.onAgentProgress?.(
          message.payload.stage,
          message.payload.detail
        );
        break;
      case 'approval_required':
        handlers.current.onApprovalRequired?.(message.payload.draft);
        break;
    }
  }, [lastJsonMessage]);

  const sendMessage = useCallback(
    (content: string) => {
      sendJsonMessage({ action: 'send_message', payload: { content } });
    },
    [sendJsonMessage]
  );

  const submitApproval = useCallback(
    (approved: boolean, content?: string) => {
      sendJsonMessage({
        action: 'approval_decision',
        payload: { approved, content: content ?? null },
      });
    },
    [sendJsonMessage]
  );

  return {
    sendMessage,
    submitApproval,
    isConnected: readyState === ReadyState.OPEN,
    readyState,
  };
}
