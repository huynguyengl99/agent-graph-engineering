/**
 * Generated from the backend OpenAPI schema.
 *
 * DO NOT EDIT. Run `pnpm gen:type` to regenerate.
 */

export interface AIResponseEvent {
  id: number;
  eventType: string;
  createdBy: User;
  createdAt: string;
  content: string;
  modelName?: string;
  tokensUsed?: number;
}

export interface AIResponseEventTyped {
  id: number;
  eventType: "ai_response";
  createdBy: User;
  createdAt: string;
  content: string;
  modelName?: string;
  tokensUsed?: number;
}

export interface AssignmentEvent {
  id: number;
  eventType: string;
  createdBy: User;
  createdAt: string;
  oldAssignee: User;
  newAssignee: User;
}

export interface AssignmentEventTyped {
  id: number;
  eventType: "assignment";
  createdBy: User;
  createdAt: string;
  oldAssignee: User;
  newAssignee: User;
}

export interface CommentEvent {
  id: number;
  eventType: string;
  createdBy: User;
  createdAt: string;
  content: string;
}

export interface CommentEventCreateRequest {
  content: string;
}

export interface CommentEventTyped {
  id: number;
  eventType: "comment";
  createdBy: User;
  createdAt: string;
  content: string;
}

export interface Conversation {
  id: string;
  title?: string;
  ticket?: string | null;
  pendingApproval: PendingApproval;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationCreateRequest {
  title?: string;
  ticket?: string | null;
}

/** JWT token refresh with cookie and request data support. */
export interface CookieTokenRefresh {
  access: string;
  accessExpiration: string;
}

/** JWT token refresh with cookie and request data support. */
export interface CookieTokenRefreshRequest {
  /** Will override cookie. */
  refresh?: string;
}

/** JWT logout with refresh token blacklisting. */
export interface JWTLogout {
  detail: string;
}

/** JWT logout with refresh token blacklisting. */
export interface JWTLogoutRequest {
  refresh?: string;
}

/** User authentication with credentials response. */
export interface Login {
  access: string;
  refresh: string;
  accessExpiration: string;
  refreshExpiration: string;
  user: User;
}

/** User authentication with credentials response. */
export interface LoginRequest {
  email: string;
  password: string;
}

export interface Message {
  id: string;
  role: RoleEnum;
  content: string;
  createdAt: string;
}

export interface ModelPreference {
  purpose: PurposeEnum;
  model: string;
}

export interface ModelPreferenceRequest {
  purpose: PurposeEnum;
  model: string;
}

export interface PaginatedConversationList {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: Conversation[];
}

export interface PaginatedMessageList {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: Message[];
}

export interface PaginatedModelPreferenceList {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: ModelPreference[];
}

export interface PaginatedTicketEventPolymorphicList {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: TicketEventPolymorphic[];
}

export interface PaginatedTicketList {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: Ticket[];
}

/** Password change for authenticated users. */
export interface PasswordChange {
  detail: string;
}

/** Password change for authenticated users. */
export interface PasswordChangeRequest {
  newPassword1: string;
  newPassword2: string;
}

/** Password reset request with email verification. */
export interface PasswordReset {
  detail: string;
}

/** Password reset confirmation with new password. */
export interface PasswordResetConfirm {
  detail: string;
}

/** Password reset confirmation with new password. */
export interface PasswordResetConfirmRequest {
  newPassword1: string;
  newPassword2: string;
  uid: string;
  token: string;
}

/** Password reset request with email verification. */
export interface PasswordResetRequest {
  email: string;
}

/** Ticket update serializer. */
export interface PatchedTicketUpdateRequest {
  title?: string;
  description?: string;
  status?: TicketStatusEnum;
  priority?: PriorityEnum;
  assignedTo?: string | null;
}

/** User serializer for API responses. */
export interface PatchedUserRequest {
  email?: string;
  firstName?: string;
  lastName?: string;
}

/** Field for field the same shape the `tool_approval` frame carries, so the browser uses one type whether the proposal arrived live or on a reload. The JSON fields are declared rather than inferred: a bare `JSONField` generates `unknown` in TypeScript, which pushes a cast into every caller. */
export interface PendingApproval {
  tool: string;
  description: string;
  arguments: Record<string, unknown>;
  argumentsSchema: Record<string, unknown>;
  unknownArguments: string[];
  createdAt: string;
}

/** * `low` - Low * `medium` - Medium * `high` - High * `urgent` - Urgent */
export type PriorityEnum = "low" | "medium" | "high" | "urgent";

/** * `decision` - Decision * `answer` - Answer */
export type PurposeEnum = "decision" | "answer";

/** User registration with email verification. */
export interface Register {
  detail: string;
}

/** User registration with email verification. */
export interface RegisterRequest {
  email: string;
  password1: string;
  password2: string;
  firstName?: string;
  lastName?: string;
}

/** Request new email verification message. */
export interface ResendEmailVerification {
  detail: string;
}

/** Request new email verification message. */
export interface ResendEmailVerificationRequest {
  email: string;
}

/** * `user` - User * `assistant` - Assistant */
export type RoleEnum = "user" | "assistant";

export interface StatusChangeEvent {
  id: number;
  eventType: string;
  createdBy: User;
  createdAt: string;
  oldStatus: TicketStatusEnum;
  newStatus: TicketStatusEnum;
}

export interface StatusChangeEventTyped {
  id: number;
  eventType: "status_change";
  createdBy: User;
  createdAt: string;
  oldStatus: TicketStatusEnum;
  newStatus: TicketStatusEnum;
}

/** Full ticket serializer for read operations. */
export interface Ticket {
  id: string;
  title: string;
  description: string;
  status?: TicketStatusEnum;
  priority?: PriorityEnum;
  createdBy: User;
  assignedTo: User;
  createdAt: string;
  updatedAt: string;
}

/** Ticket creation serializer. */
export interface TicketCreateRequest {
  title: string;
  description: string;
  priority?: PriorityEnum;
}

/** Discriminated on `eventType`. */
export type TicketEventPolymorphic =
  | CommentEventTyped
  | StatusChangeEventTyped
  | AssignmentEventTyped
  | AIResponseEventTyped;

/** * `open` - Open * `in_progress` - In Progress * `resolved` - Resolved * `closed` - Closed */
export type TicketStatusEnum = "open" | "in_progress" | "resolved" | "closed";

/** Ticket update serializer. */
export interface TicketUpdate {
  title: string;
  description: string;
  status?: TicketStatusEnum;
  priority?: PriorityEnum;
  assignedTo?: string | null;
}

/** Ticket update serializer. */
export interface TicketUpdateRequest {
  title: string;
  description: string;
  status?: TicketStatusEnum;
  priority?: PriorityEnum;
  assignedTo?: string | null;
}

export interface TokenVerifyRequest {
  token: string;
}

/** User serializer for API responses. */
export interface User {
  id: string;
  email: string;
  firstName?: string;
  lastName?: string;
  fullName: string;
  dateJoined: string;
}

/** User serializer for API responses. */
export interface UserRequest {
  email: string;
  firstName?: string;
  lastName?: string;
}

/** Email address verification with confirmation key. */
export interface VerifyEmail {
  detail: string;
}

/** Email address verification with confirmation key. */
export interface VerifyEmailRequest {
  key: string;
}
