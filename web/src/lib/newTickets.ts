/** Tickets created in this tab, so their thread knows to hand the opening
 *  message to the agent exactly once. */
export const awaitingFirstReply = new Set<string>();
