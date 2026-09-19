/**
 * Generated WebSocket schema types
 *
 * DO NOT EDIT - Auto-generated from AsyncAPI
 * Run `pnpm gen:ws` to regenerate
 */

export interface AgentProgressMessage {
  action?: string;
  payload: AgentProgressPayload;
}

export interface AgentProgressPayload {
  stage: string;
  detail: string;
}

export interface CompleteStreamingMessage {
  action?: string;
  payload: CompleteStreamingPayload;
}

export interface CompleteStreamingPayload {
  event: Record<string, any>;
}

export interface NewEventMessage {
  action?: string;
  payload: NewEventPayload;
}

export interface NewEventPayload {
  event: Record<string, any>;
}

export interface PingMessage {
  action?: string;
  payload?: any;
}

export interface PongMessage {
  action?: string;
  payload?: any;
}

export interface SendMessageMessage {
  action?: string;
  payload: SendMessagePayload;
}

export interface SendMessagePayload {
  content: string;
}

export interface StreamingMessage {
  action?: string;
  payload: StreamingPayload;
}

export interface StreamingPayload {
  chunk: string;
}
