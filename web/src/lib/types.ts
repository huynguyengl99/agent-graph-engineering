/**
 * Application-facing types, inferred from the generated Zod schemas.
 *
 * Two generators describe the same API: `src/types/backend` (types only, for
 * consumers that do not want a client) and `src/schemas/backend` (Zod schemas
 * plus a Zodios client). The app uses the Zod-inferred ones, because those are
 * the shapes actually validated at runtime, and because Zodios returns them
 * directly from every call.
 */

import type { z } from 'zod';
import { schemas } from '@/schemas/backend';
import type {
  ChatMessage as WireChatMessage,
  NewEventPayload,
} from '@/generated';

export type Ticket = z.infer<typeof schemas.Ticket>;
/**
 * One canonical event type for both transports.
 *
 * REST and the WebSocket now describe the same polymorphic union, so the app
 * uses the WS-generated interfaces: they are clean discriminated interfaces
 * rather than Zod `.passthrough()` objects, and they narrow on `eventType`.
 */
export type TicketEvent = NewEventPayload['event'];
export type User = z.infer<typeof schemas.User>;
export type Conversation = z.infer<typeof schemas.Conversation>;
/**
 * The realtime declaration, used for REST-fetched messages too.
 *
 * Same reasoning as `TicketEvent`: the backend builds this payload from the
 * REST serializer, so one type covers the page load and the feed. Typing them
 * separately is what let `assistant_done` drift into a third shape and the
 * client invent a `createdAt` the database had already set.
 */
export type ChatMessage = WireChatMessage;
