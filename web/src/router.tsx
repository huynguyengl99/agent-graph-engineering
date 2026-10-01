import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router';
import { RootLayout } from '@/routes/root';
import { TicketsIndex } from '@/routes/index';
import { TicketRoute } from '@/routes/ticket';
import { ChatRoute } from '@/routes/chat';
import { GraphsRoute } from '@/routes/graphs';
import { SettingsRoute } from '@/routes/settings';

// Code-based routes rather than file-based: five of them, and it keeps the
// build free of a route-tree generator step.
const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: TicketsIndex,
});

const ticketRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/tickets/$ticketId',
  component: function Ticket() {
    const { ticketId } = ticketRoute.useParams();
    return <TicketRoute key={ticketId} ticketId={ticketId} />;
  },
});

const chatIndexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  component: function ChatIndex() {
    return (
      <p className="p-8 text-gray-500">
        Pick a conversation, or start a new one.
      </p>
    );
  },
});

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat/$conversationId',
  component: function Chat() {
    const { conversationId } = chatRoute.useParams();
    return <ChatRoute key={conversationId} conversationId={conversationId} />;
  },
});

const graphsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/graphs',
  component: GraphsRoute,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: SettingsRoute,
});

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    indexRoute,
    ticketRoute,
    chatIndexRoute,
    chatRoute,
    graphsRoute,
    settingsRoute,
  ]),
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
