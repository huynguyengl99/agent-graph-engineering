import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router';
import { RootLayout } from '@/routes/root';
import { TicketsIndex } from '@/routes/index';
import { TicketRoute } from '@/routes/ticket';

// Code-based routes rather than file-based: three of them, and it keeps the
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

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, ticketRoute]),
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
