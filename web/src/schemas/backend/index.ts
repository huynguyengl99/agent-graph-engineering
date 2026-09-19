import { makeApi, Zodios, type ZodiosOptions } from "@zodios/core";
import { z } from "zod";

const LoginRequest = z
  .object({ email: z.string().min(1).email(), password: z.string().min(1) })
  .passthrough();
const User = z
  .object({
    id: z.string().uuid(),
    email: z.string().max(255).email(),
    firstName: z.string().max(150).optional(),
    lastName: z.string().max(150).optional(),
    fullName: z.string(),
    dateJoined: z.string().datetime({ offset: true }),
  })
  .passthrough();
const Login = z
  .object({
    access: z.string(),
    refresh: z.string(),
    accessExpiration: z.string().datetime({ offset: true }),
    refreshExpiration: z.string().datetime({ offset: true }),
    user: User,
  })
  .passthrough();
const JWTLogoutRequest = z
  .object({ refresh: z.string().min(1) })
  .partial()
  .passthrough();
const JWTLogout = z.object({ detail: z.string() }).passthrough();
const PasswordChangeRequest = z
  .object({
    newPassword1: z.string().min(1).max(128),
    newPassword2: z.string().min(1).max(128),
  })
  .passthrough();
const PasswordChange = z.object({ detail: z.string() }).passthrough();
const PasswordResetRequest = z
  .object({ email: z.string().min(1).email() })
  .passthrough();
const PasswordReset = z.object({ detail: z.string() }).passthrough();
const PasswordResetConfirmRequest = z
  .object({
    newPassword1: z.string().min(1).max(128),
    newPassword2: z.string().min(1).max(128),
    uid: z.string().min(1),
    token: z.string().min(1),
  })
  .passthrough();
const PasswordResetConfirm = z.object({ detail: z.string() }).passthrough();
const RegisterRequest = z
  .object({
    email: z.string().min(1).email(),
    password1: z.string().min(1),
    password2: z.string().min(1),
    firstName: z.string().optional(),
    lastName: z.string().optional(),
  })
  .passthrough();
const Register = z.object({ detail: z.string() }).passthrough();
const ResendEmailVerificationRequest = z
  .object({ email: z.string().min(1).email() })
  .passthrough();
const ResendEmailVerification = z.object({ detail: z.string() }).passthrough();
const VerifyEmailRequest = z.object({ key: z.string().min(1) }).passthrough();
const VerifyEmail = z.object({ detail: z.string() }).passthrough();
const CookieTokenRefreshRequest = z
  .object({ refresh: z.string() })
  .partial()
  .passthrough();
const CookieTokenRefresh = z
  .object({
    access: z.string(),
    accessExpiration: z.string().datetime({ offset: true }),
  })
  .passthrough();
const TokenVerifyRequest = z.object({ token: z.string().min(1) }).passthrough();
const UserRequest = z
  .object({
    email: z.string().min(1).max(255).email(),
    firstName: z.string().max(150).optional(),
    lastName: z.string().max(150).optional(),
  })
  .passthrough();
const PatchedUserRequest = z
  .object({
    email: z.string().min(1).max(255).email(),
    firstName: z.string().max(150),
    lastName: z.string().max(150),
  })
  .partial()
  .passthrough();
const NewStatusEnum = z.enum(["open", "in_progress", "resolved", "closed"]);
const PriorityEnum = z.enum(["low", "medium", "high", "urgent"]);
const Ticket = z
  .object({
    id: z.string().uuid(),
    title: z.string().max(255),
    description: z.string(),
    status: NewStatusEnum.optional(),
    priority: PriorityEnum.optional(),
    createdBy: User,
    assignedTo: User.nullable(),
    createdAt: z.string().datetime({ offset: true }),
    updatedAt: z.string().datetime({ offset: true }),
  })
  .passthrough();
const PaginatedTicketList = z
  .object({
    count: z.number().int(),
    next: z.string().url().nullish(),
    previous: z.string().url().nullish(),
    results: z.array(Ticket),
  })
  .passthrough();
const TicketCreateRequest = z
  .object({
    title: z.string().min(1).max(255),
    description: z.string().min(1),
    priority: PriorityEnum.optional(),
  })
  .passthrough();
const TicketCreate = z
  .object({
    title: z.string().max(255),
    description: z.string(),
    priority: PriorityEnum.optional(),
  })
  .passthrough();
const TicketUpdateRequest = z
  .object({
    title: z.string().min(1).max(255),
    description: z.string().min(1),
    status: NewStatusEnum.optional(),
    priority: PriorityEnum.optional(),
    assignedTo: z.string().uuid().nullish(),
  })
  .passthrough();
const TicketUpdate = z
  .object({
    title: z.string().max(255),
    description: z.string(),
    status: NewStatusEnum.optional(),
    priority: PriorityEnum.optional(),
    assignedTo: z.string().uuid().nullish(),
  })
  .passthrough();
const PatchedTicketUpdateRequest = z
  .object({
    title: z.string().min(1).max(255),
    description: z.string().min(1),
    status: NewStatusEnum,
    priority: PriorityEnum,
    assignedTo: z.string().uuid().nullable(),
  })
  .partial()
  .passthrough();
const CommentEventTyped = z
  .object({
    id: z.number().int(),
    eventType: z.literal("comment"),
    createdBy: User.nullable(),
    createdAt: z.string().datetime({ offset: true }),
    content: z.string(),
  })
  .passthrough();
const StatusChangeEventTyped = z
  .object({
    id: z.number().int(),
    eventType: z.literal("status_change"),
    createdBy: User.nullable(),
    createdAt: z.string().datetime({ offset: true }),
    oldStatus: NewStatusEnum,
    newStatus: NewStatusEnum,
  })
  .passthrough();
const AssignmentEventTyped = z
  .object({
    id: z.number().int(),
    eventType: z.literal("assignment"),
    createdBy: User.nullable(),
    createdAt: z.string().datetime({ offset: true }),
    oldAssignee: User.nullable(),
    newAssignee: User.nullable(),
  })
  .passthrough();
const AIResponseEventTyped = z
  .object({
    id: z.number().int(),
    eventType: z.literal("ai_response"),
    createdBy: User.nullable(),
    createdAt: z.string().datetime({ offset: true }),
    content: z.string(),
    modelName: z.string().max(100).optional(),
    tokensUsed: z.number().int().gte(-2147483648).lte(2147483647).optional(),
  })
  .passthrough();
const TicketEventPolymorphic = z.discriminatedUnion("eventType", [
  CommentEventTyped,
  StatusChangeEventTyped,
  AssignmentEventTyped,
  AIResponseEventTyped,
]);
const PaginatedTicketEventPolymorphicList = z
  .object({
    count: z.number().int(),
    next: z.string().url().nullish(),
    previous: z.string().url().nullish(),
    results: z.array(TicketEventPolymorphic),
  })
  .passthrough();
const CommentEventCreateRequest = z
  .object({ content: z.string().min(1) })
  .passthrough();

export const schemas = {
  LoginRequest,
  User,
  Login,
  JWTLogoutRequest,
  JWTLogout,
  PasswordChangeRequest,
  PasswordChange,
  PasswordResetRequest,
  PasswordReset,
  PasswordResetConfirmRequest,
  PasswordResetConfirm,
  RegisterRequest,
  Register,
  ResendEmailVerificationRequest,
  ResendEmailVerification,
  VerifyEmailRequest,
  VerifyEmail,
  CookieTokenRefreshRequest,
  CookieTokenRefresh,
  TokenVerifyRequest,
  UserRequest,
  PatchedUserRequest,
  NewStatusEnum,
  PriorityEnum,
  Ticket,
  PaginatedTicketList,
  TicketCreateRequest,
  TicketCreate,
  TicketUpdateRequest,
  TicketUpdate,
  PatchedTicketUpdateRequest,
  CommentEventTyped,
  StatusChangeEventTyped,
  AssignmentEventTyped,
  AIResponseEventTyped,
  TicketEventPolymorphic,
  PaginatedTicketEventPolymorphicList,
  CommentEventCreateRequest,
};

const endpoints = makeApi([
  {
    method: "post",
    path: "/api/accounts/login/",
    description: `Authenticate with username/email and password to obtain access tokens. Returns user details along with JWT access and refresh tokens with expiration times. Authentication cookies are set automatically for secure token storage.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: LoginRequest,
      },
    ],
    response: Login,
  },
  {
    method: "post",
    path: "/api/accounts/logout/",
    description: `Logout user and invalidate authentication tokens. Blacklists JWT refresh tokens to prevent further use. Clears authentication cookies from the browser. Requires authentication to ensure only valid sessions can be logged out.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z
          .object({ refresh: z.string().min(1) })
          .partial()
          .passthrough(),
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "post",
    path: "/api/accounts/password/change/",
    description: `Change the current user&#x27;s password. Requires authentication. `,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: PasswordChangeRequest,
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "post",
    path: "/api/accounts/password/reset/",
    description: `Send password reset instructions to the provided email address. If the email is registered, a secure reset link will be sent. The link expires after a limited time for security.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z.object({ email: z.string().min(1).email() }).passthrough(),
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "post",
    path: "/api/accounts/password/reset/confirm/",
    description: `Complete the password reset process using the token from the reset email. Requires the UID and token from the email along with the new password. The token is single-use and expires for security.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: PasswordResetConfirmRequest,
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "post",
    path: "/api/accounts/registration/",
    description: `Register a new user account.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: RegisterRequest,
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "post",
    path: "/api/accounts/registration/resend-email/",
    description: `Send a new email verification message to unverified email addresses. Only works for email addresses that are registered but not yet verified.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z.object({ email: z.string().min(1).email() }).passthrough(),
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "get",
    path: "/api/accounts/registration/verify-email/",
    description: `GET method not allowed for email verification.`,
    requestFormat: "json",
    response: z.void(),
  },
  {
    method: "post",
    path: "/api/accounts/registration/verify-email/",
    description: `Confirm email address using the verification key sent via email. This activates the user account and allows login access.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z.object({ key: z.string().min(1) }).passthrough(),
      },
    ],
    response: z.object({ detail: z.string() }).passthrough(),
  },
  {
    method: "post",
    path: "/api/accounts/token/refresh/",
    description: `Generate new JWT access tokens using refresh tokens. Refresh tokens can be provided in request data or extracted automatically from HTTP cookies. Returns new access tokens with updated expiration times. New tokens are automatically set in HTTP cookies for secure storage.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z.object({ refresh: z.string() }).partial().passthrough(),
      },
    ],
    response: CookieTokenRefresh,
  },
  {
    method: "post",
    path: "/api/accounts/token/verify/",
    description: `Takes a token and indicates if it is valid.  This view provides no
information about a token&#x27;s fitness for a particular use.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z.object({ token: z.string().min(1) }).passthrough(),
      },
    ],
    response: z.void(),
  },
  {
    method: "get",
    path: "/api/accounts/user/",
    description: `Retrieve the authenticated user&#x27;s profile information including username, email, first name, and last name. Password fields are excluded.`,
    requestFormat: "json",
    response: User,
  },
  {
    method: "put",
    path: "/api/accounts/user/",
    description: `Update the authenticated user&#x27;s profile information. Allows modification of username, first name, and last name. Email field is read-only for security.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: UserRequest,
      },
    ],
    response: User,
  },
  {
    method: "patch",
    path: "/api/accounts/user/",
    description: `Partially update the authenticated user&#x27;s profile information. Only provided fields will be updated. Email field is read-only.`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: PatchedUserRequest,
      },
    ],
    response: User,
  },
  {
    method: "get",
    path: "/api/schema/no-error/",
    description: `Return OpenAPI schema without error schemas.`,
    requestFormat: "json",
    parameters: [
      {
        name: "format",
        type: "Query",
        schema: z.enum(["json", "yaml"]).optional(),
      },
    ],
    response: z.void(),
  },
  {
    method: "get",
    path: "/api/tickets/",
    description: `Get paginated list of tickets with filtering and search`,
    requestFormat: "json",
    parameters: [
      {
        name: "assigned_to",
        type: "Query",
        schema: z.string().uuid().optional(),
      },
      {
        name: "ordering",
        type: "Query",
        schema: z.string().optional(),
      },
      {
        name: "page",
        type: "Query",
        schema: z.number().int().optional(),
      },
      {
        name: "priority",
        type: "Query",
        schema: z.enum(["high", "low", "medium", "urgent"]).optional(),
      },
      {
        name: "search",
        type: "Query",
        schema: z.string().optional(),
      },
      {
        name: "status",
        type: "Query",
        schema: z
          .enum(["closed", "in_progress", "open", "resolved"])
          .optional(),
      },
    ],
    response: PaginatedTicketList,
  },
  {
    method: "post",
    path: "/api/tickets/",
    description: `Create a new support ticket`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: TicketCreateRequest,
      },
    ],
    response: TicketCreate,
  },
  {
    method: "get",
    path: "/api/tickets/:id/",
    description: `Get detailed information about a specific ticket`,
    requestFormat: "json",
    parameters: [
      {
        name: "id",
        type: "Path",
        schema: z.string().uuid(),
      },
    ],
    response: Ticket,
  },
  {
    method: "put",
    path: "/api/tickets/:id/",
    description: `Update an existing ticket (full update)`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: TicketUpdateRequest,
      },
      {
        name: "id",
        type: "Path",
        schema: z.string().uuid(),
      },
    ],
    response: TicketUpdate,
  },
  {
    method: "patch",
    path: "/api/tickets/:id/",
    description: `Partially update an existing ticket`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: PatchedTicketUpdateRequest,
      },
      {
        name: "id",
        type: "Path",
        schema: z.string().uuid(),
      },
    ],
    response: TicketUpdate,
  },
  {
    method: "delete",
    path: "/api/tickets/:id/",
    description: `Delete a ticket`,
    requestFormat: "json",
    parameters: [
      {
        name: "id",
        type: "Path",
        schema: z.string().uuid(),
      },
    ],
    response: z.void(),
  },
  {
    method: "get",
    path: "/api/tickets/:ticketPk/events/",
    description: `Get all events for a ticket (polymorphic - returns mixed event types)`,
    requestFormat: "json",
    parameters: [
      {
        name: "ordering",
        type: "Query",
        schema: z.string().optional(),
      },
      {
        name: "page",
        type: "Query",
        schema: z.number().int().optional(),
      },
      {
        name: "search",
        type: "Query",
        schema: z.string().optional(),
      },
      {
        name: "ticketPk",
        type: "Path",
        schema: z.string(),
      },
    ],
    response: PaginatedTicketEventPolymorphicList,
  },
  {
    method: "post",
    path: "/api/tickets/:ticketPk/events/",
    description: `Add a comment to the ticket`,
    requestFormat: "json",
    parameters: [
      {
        name: "body",
        type: "Body",
        schema: z.object({ content: z.string().min(1) }).passthrough(),
      },
      {
        name: "ticketPk",
        type: "Path",
        schema: z.string(),
      },
    ],
    response: TicketEventPolymorphic,
  },
]);

export const api = new Zodios(endpoints);

export function createApiClient(baseUrl: string, options?: ZodiosOptions) {
  return new Zodios(baseUrl, endpoints, options);
}
