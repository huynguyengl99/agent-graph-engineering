import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router';
import { RootLayout } from '@/routes/root';
import { TicketsIndex } from '@/routes/index';
import { TicketRoute } from '@/routes/ticket';
import { GraphsRoute } from '@/routes/graphs';
import { SettingsRoute } from '@/routes/settings';
import { TracesRoute } from '@/routes/traces';
import { PortalIndex, PortalLayout, PortalTicketRoute } from '@/routes/portal';

// Code-based routes rather than file-based: it keeps the build free of a
// route-tree generator step.
//
// Two layouts under one root. The console and the portal are the same app and
// the same session; which one an account gets is decided by `isStaff`.
const rootRoute = createRootRoute();

const consoleRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'console',
  component: RootLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => consoleRoute,
  path: '/',
  component: TicketsIndex,
});

const ticketRoute = createRoute({
  getParentRoute: () => consoleRoute,
  path: '/tickets/$ticketId',
  component: function Ticket() {
    const { ticketId } = ticketRoute.useParams();
    return <TicketRoute key={ticketId} ticketId={ticketId} />;
  },
});

const graphsRoute = createRoute({
  getParentRoute: () => consoleRoute,
  path: '/graphs',
  component: GraphsRoute,
});

const tracesRoute = createRoute({
  getParentRoute: () => consoleRoute,
  path: '/traces',
  component: TracesRoute,
});

const settingsRoute = createRoute({
  getParentRoute: () => consoleRoute,
  path: '/settings',
  component: SettingsRoute,
});

const portalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/portal',
  component: PortalLayout,
});

const portalIndexRoute = createRoute({
  getParentRoute: () => portalRoute,
  path: '/',
  component: PortalIndex,
});

const portalTicketRoute = createRoute({
  getParentRoute: () => portalRoute,
  path: 'tickets/$ticketId',
  component: function PortalTicket() {
    const { ticketId } = portalTicketRoute.useParams();
    return <PortalTicketRoute key={ticketId} ticketId={ticketId} />;
  },
});

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    consoleRoute.addChildren([
      indexRoute,
      ticketRoute,
      graphsRoute,
      tracesRoute,
      settingsRoute,
    ]),
    portalRoute.addChildren([portalIndexRoute, portalTicketRoute]),
  ]),
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
