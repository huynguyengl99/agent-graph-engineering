/**
 * One pass through the whole product against the real services.
 *
 * Every other test here mocks something: the unit tests mock the model, the
 * backend tests mock the agent. This one mocks nothing, which is why it has
 * caught what the others could not - a Zodios client that threw on import, a
 * generated contract that disagreed with its schema, a dependency upgrade
 * that changed how models are constructed.
 *
 *   just e2e        # with all three services running
 *
 * It writes to the dev database and spends real tokens, so it is not part of
 * `just test`.
 */

import { chromium } from 'playwright';

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:5173';
const EMAIL = process.env.E2E_EMAIL ?? 'demo@example.com';
const PASSWORD = process.env.E2E_PASSWORD ?? 'demo-pass-123';
const results = [];
const ok = (m) => { console.log('  PASS ', m); results.push(true); };
const bad = (m) => { console.log('  FAIL ', m); results.push(false); };

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
const sockets = [];
const stages = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('websocket', (ws) => {
  sockets.push(ws.url());
  if (!ws.url().includes('/ws/')) return;
  // Progress is transient in the UI - the pane clears it the moment the final
  // answer lands - so the frames are the durable record of what the server
  // actually sent. Asserting on the DOM here is a race the fast path wins.
  ws.on('framereceived', (f) => {
    try {
      const m = JSON.parse(f.payload);
      if (m.action === 'agent_progress') stages.push(m.payload.stage);
    } catch {
      /* not JSON: heartbeat or control frame */
    }
  });
});

const sawStage = async (name, timeout = 60000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (stages.includes(name)) return true;
    await page.waitForTimeout(250);
  }
  return false;
};

async function login() {
  await page.goto(BASE);
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForSelector('a[href^="/tickets/"]', { timeout: 20000 });
}

console.log('== auth + ticket list ==');
await login();
ok('logged in and the ticket list rendered');

console.log('== ticket triage, end to end ==');
// A fresh ticket per run. Sharing one meant every run appended a comment, and
// a ticket with eight identical complaints eventually routes to escalation -
// which correctly has no approval gate, so the run "failed" on a correct
// decision.
const ticketId = await page.evaluate(async () => {
  const response = await fetch('/api/tickets/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      title: 'Charged twice this month',
      description: 'My card shows two charges for the same plan.',
      status: 'open',
      priority: 'medium',
    }),
  });
  if (!response.ok) throw new Error(`ticket create: ${response.status}`);
  return (await response.json()).id;
});
ok(`created a fresh ticket for this run (${String(ticketId).slice(0, 8)})`);
await page.goto(`${BASE}/tickets/${ticketId}`);
await page.waitForSelector('text=live', { timeout: 20000 });
await page.fill('main form input[placeholder]', 'I was charged twice for my plan this month.');
await page.click('main form button[type="submit"]');
(await sawStage('classified'))
  ? ok('the classification reached the browser')
  : bad('no classified stage arrived');
(await sawStage('decided'))
  ? ok('the routing decision reached the browser')
  : bad('no decided stage arrived');
await page.waitForSelector('button:has-text("Approve")', { timeout: 60000 });
ok('the run parked at the human approval gate');
await page.click('button:has-text("Approve")');
await page.waitForSelector('li:has-text("Agent (")', { timeout: 60000 });
ok('the approved reply was persisted and broadcast back');

console.log('== rep chat, streaming + persistence ==');
await page.click('button:has-text("Ask the assistant")');
await page.waitForURL(/\/chat\/[0-9a-f-]+$/, { timeout: 20000 });
const chatUrl = page.url();
ok('ticket opened a conversation carrying its ticket');
await page.fill('main form input[placeholder]', 'What should I tell them about the double charge?');
await page.click('main button:has-text("Ask")');
await page.waitForSelector('text=answering…', { timeout: 30000 });
ok('the answer started streaming');
await page.waitForSelector('main button:has-text("Send this to the ticket")', { timeout: 90000 });
ok('the answer finished and can be sent to the ticket');
const before = await page.locator('main ul li').allInnerTexts();
await page.reload();
await page.waitForSelector('main button:has-text("Send this to the ticket")', { timeout: 30000 });
const after = await page.locator('main ul li').allInnerTexts();
JSON.stringify(before) === JSON.stringify(after)
  ? ok(`conversation survived a reload (${after.length} turns, identical)`)
  : bad(`reload changed the conversation: ${before.length} -> ${after.length}`);

console.log('== graph diagrams ==');
await page.click('a[href="/graphs"]');
await page.waitForSelector('main svg', { state: 'attached', timeout: 30000 });
const expanded = await page.locator('main svg').innerHTML();
['await_approval', 'refine', 'screen'].every((n) => expanded.includes(n))
  ? ok('xray expands both subgraphs inline')
  : bad('xray did not expand the subgraphs');
await page.uncheck('input[type="checkbox"]');
await page.waitForTimeout(1500);
const collapsed = await page.locator('main svg').innerHTML();
!collapsed.includes('await_approval') && collapsed.includes('delivery')
  ? ok('collapsed shows subgraphs as single nodes')
  : bad('collapse did not work');

console.log('== one socket for everything ==');
const app = sockets.filter((u) => u.includes('/ws/'));
app.length <= 3
  ? ok(`${app.length} app socket(s) across the whole session (reloads included)`)
  : bad(`${app.length} app sockets - expected one per page load`);

errors.length === 0 ? ok('no page errors') : bad(`page errors: ${errors.join(' | ')}`);

await page.screenshot({ path: 'e2e/last-run.png', fullPage: true });
await browser.close();

const failed = results.filter((r) => !r).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
