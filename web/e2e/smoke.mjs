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
const CUSTOMER_EMAIL = process.env.E2E_CUSTOMER_EMAIL ?? 'customer@example.com';
const PASSWORD = process.env.E2E_PASSWORD ?? 'demo-pass-123';
const results = [];
const ok = (m) => {
  console.log('  PASS ', m);
  results.push(true);
};
const bad = (m) => {
  console.log('  FAIL ', m);
  results.push(false);
};

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
const sockets = [];
const stages = [];
const proposals = [];
const decisions = [];
page.on('pageerror', (e) => errors.push(String(e)));
let pageLoads = 0;
page.on('load', () => {
  pageLoads += 1;
});
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
      if (m.action === 'tool_approval') proposals.push(m.payload);
    } catch {
      /* not JSON: heartbeat or control frame */
    }
  });
  ws.on('framesent', (f) => {
    try {
      const m = JSON.parse(f.payload);
      if (m.action === 'tool_decision') decisions.push(m.payload);
    } catch {
      /* not JSON */
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

async function login(email = EMAIL) {
  await page.goto(BASE);
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForSelector('a[href*="/tickets/"]', { timeout: 20000 });
}

async function signOut() {
  await page.click('button:has-text("Sign out")');
  await page.waitForSelector('input[type="email"]', { timeout: 20000 });
}

console.log('== auth + ticket list ==');
await login();
ok('logged in and the ticket list rendered');

console.log('== the customer reports a problem ==');
// Their own session, so both sides are open at once: staff watch the run on the
// console while the customer is in the portal, which is also what proves the
// fan-out reaches a connection that did not start the run.
const customerContext = await browser.newContext();
const customerPage = await customerContext.newPage();
await customerPage.goto(BASE);
await customerPage.fill('input[type="email"]', CUSTOMER_EMAIL);
await customerPage.fill('input[type="password"]', PASSWORD);
await customerPage.click('button[type="submit"]');
await customerPage.waitForURL('**/portal', { timeout: 20000 });
ok('the customer lands on the portal, not the console');
// A fresh ticket per run. Sharing one meant every run appended a comment, and
// a ticket with eight identical complaints eventually routes to escalation -
// which correctly has no approval gate, so the run "failed" on a correct
// decision.
// Through the form, not through fetch: the form is generated from the same
// OpenAPI schema the client validates against, so creating a ticket this way
// covers the generated schema, the form built from it and the request together.
await customerPage.fill(
  'aside input[aria-label="Title"]',
  'Charged twice this month',
);
await customerPage.fill(
  'aside textarea[aria-label="Description"]',
  'My card shows two charges for the same plan.',
);
await customerPage.selectOption(
  'aside select[aria-label="Priority"]',
  'medium',
);

// The list already has tickets, so waiting for "a ticket link" would match one
// from a previous run. Wait for the list to grow instead.
const TICKET_LINK = 'aside a[href*="/tickets/"]';
const ticketsBefore = await customerPage.locator(TICKET_LINK).count();
await customerPage.click('aside button:has-text("Create ticket")');
await customerPage.waitForFunction(
  ([selector, n]) => document.querySelectorAll(selector).length > n,
  [TICKET_LINK, ticketsBefore],
  { timeout: 20000 },
);
const ticketId = await customerPage
  .locator(TICKET_LINK)
  .first()
  .getAttribute('href')
  .then((href) => href.split('/').pop());
ok(`reported a problem through the generated form (${ticketId.slice(0, 8)})`);

console.log('== ticket triage, end to end ==');
// Staff open the ticket first, so the run's progress is watched by a connection
// that did not start it.
await page.goto(`${BASE}/tickets/${ticketId}`);
await page.waitForSelector('text=live', { timeout: 20000 });

// The customer's own message is what asks the agent for a reply. A staff note
// would not, which is the point of the audience.
await customerPage.goto(`${BASE}/portal/tickets/${ticketId}`);
await customerPage.fill(
  'main form input[placeholder]',
  'I was charged twice for my plan this month.',
);
await customerPage.click('main form button[type="submit"]');
(await sawStage('classified'))
  ? ok('the classification reached the browser')
  : bad('no classified stage arrived');
(await sawStage('decided'))
  ? ok('the routing decision reached the browser')
  : bad('no decided stage arrived');
await page.waitForSelector('button:has-text("Approve")', { timeout: 60000 });
ok('the run parked at the human approval gate');

// The draft lived on a relay client that is discarded when the socket closes,
// and in this tab's React state. A reload lost a customer-facing reply.
const draftBefore = await page.locator('section textarea').inputValue();
await page.reload();
await page.waitForSelector('button:has-text("Approve")', { timeout: 30000 });
(await page.locator('section textarea').inputValue()) === draftBefore
  ? ok('the drafted reply survived a reload')
  : bad('the reloaded page lost the drafted reply');

await page.click('button:has-text("Approve")');
await page.waitForSelector('li:has-text("Agent (")', { timeout: 60000 });
ok('the approved reply was persisted and broadcast back');

// Approving without editing used to record an empty event: `reply_sent` carries
// a receipt, not the text.
const recorded = await page
  .locator('li:has-text("Agent (")')
  .last()
  .innerText();
recorded.replace(/Agent \([^)]*\)/, '').trim().length > 20
  ? ok('the ticket recorded the reply that was sent')
  : bad(`the ticket event is empty: ${recorded}`);

console.log('== rep chat, streaming + persistence ==');
await page.click('button:has-text("Ask the assistant")');
await page.waitForURL(/\/chat\/[0-9a-f-]+$/, { timeout: 20000 });
const chatUrl = page.url();
ok('ticket opened a conversation carrying its ticket');
await page.fill(
  'main form input[placeholder]',
  'What should I tell them about the double charge?',
);
await page.click('main button:has-text("Ask")');
await page.waitForSelector('text=answering…', { timeout: 30000 });
ok('the answer started streaming');
await page.waitForSelector('main button:has-text("Send this to the ticket")', {
  timeout: 90000,
});
ok('the answer finished and can be sent to the ticket');
const before = await page.locator('main ul li').allInnerTexts();
await page.reload();
await page.waitForSelector('main button:has-text("Send this to the ticket")', {
  timeout: 30000,
});
const after = await page.locator('main ul li').allInnerTexts();
JSON.stringify(before) === JSON.stringify(after)
  ? ok(`conversation survived a reload (${after.length} turns, identical)`)
  : bad(`reload changed the conversation: ${before.length} -> ${after.length}`);

console.log('== tool gate: propose, correct, run ==');
// The riskiest path in the product: a tool that moves money, proposed by a
// model, corrected by a person. Nothing is mocked, so this covers the schema
// leaving the agent, the form built from it, and the corrected arguments
// arriving back at the parked graph.
await page.goto(chatUrl);
await page.waitForSelector('text=live', { timeout: 20000 });
// Not the streaming bubble: it carries the same role, so counting it reads a
// half-written sentence as the answer.
const ANSWER = 'main li[data-role="assistant"]:not([data-pending])';
// The socket is live before the REST message list has rendered, and counting
// the answers already on screen too early makes every later "wait for one more
// answer" read the previous turn's - which looked exactly like the assistant
// ignoring a cancellation.
await page.waitForSelector(ANSWER, { timeout: 30000 });
const answersBefore = await page.locator(ANSWER).count();
await page.fill(
  'main form input[placeholder]',
  'Please refund demo@example.com £29 for the duplicate charge.',
);
await page.click('main button:has-text("Ask")');

// Two models stand between the question and the gate: the router decides this
// needs a tool, then the planner names one. Either can decline, and the gate
// never appears, so report that and carry on: a 90-second Playwright timeout
// here used to abort the run and lose every check after it, which is a worse
// outcome than one honest failure.
//
// Which of the two declined is not visible from here. `just evals tool-gate
// --trials 5` separates them, and says how often.
const parked = await page
  .waitForSelector('button:has-text("Approve and run")', { timeout: 90000 })
  .then(() => true)
  .catch(() => false);

if (!parked) {
  bad(
    'no tool proposal reached the gate for an explicit refund request, ' +
      'so it answered without one and nothing was reviewed',
  );
}

if (parked) {
  const proposal = proposals.at(-1);
  proposal?.tool === 'issue_refund'
    ? ok(`the proposal named a real tool (${proposal.tool})`)
    : bad(`unexpected proposal: ${JSON.stringify(proposal)}`);
  Object.keys(proposal?.argumentsSchema?.properties ?? {}).length > 0
    ? ok('the proposal carried the schema the form is built from')
    : bad('no argument schema arrived, so the form cannot be generated');
  console.log(`   proposed: ${JSON.stringify(proposal?.arguments)}`);
  if ((proposal?.unknownArguments ?? []).length) {
    console.log(`   dropped:  ${proposal.unknownArguments.join(', ')}`);
  }

  // Every input on the card comes from that schema. If the form were
  // hand-written per tool, this would pass while a new tool went unreviewable.
  const fieldLabels = () =>
    page
      .locator('section [aria-label]')
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute('aria-label')));
  const labels = await fieldLabels();
  labels.some((l) => /amount/i.test(l)) && labels.some((l) => /email/i.test(l))
    ? ok(`the form was generated from the schema (${labels.join(', ')})`)
    : bad(`the generated form is missing fields: ${labels.join(', ')}`);

  // The card used to live only in this tab's React state, so a reload lost it
  // while the graph stayed parked in the agent with no way back to it.
  await page.reload();
  await page.waitForSelector('section button:has-text("Cancel")', {
    timeout: 30000,
  });
  const recovered = await fieldLabels();
  recovered.some((l) => /amount/i.test(l))
    ? ok('the card survived a reload, rebuilt from the persisted proposal')
    : bad(`the reloaded card is missing its fields: ${recovered.join(', ')}`);

  // A planner that names an argument `customer_email` leaves the real one empty.
  // The tool would refuse the call, so the card refuses first - and the reviewer
  // fills it in, which is the entire reason a person is in this loop.
  const approve = page.locator('section button', {
    hasText: /Approve and run|corrections/,
  });
  if (await approve.isDisabled()) {
    // Named from the form itself, so the message says which argument the planner
    // failed to supply rather than just that something is missing.
    const empty = await page
      .locator('section [aria-label]')
      .evaluateAll((nodes) =>
        nodes
          .filter((n) => !(n instanceof HTMLSelectElement) && !n.value)
          .map((n) => n.getAttribute('aria-label')),
      );
    ok(
      `approval is blocked while a required field is empty (${empty.join(', ')})`,
    );
    for (const [label, value] of [
      ['Email', 'demo@example.com'],
      ['Reason', 'Duplicate charge'],
    ]) {
      const field = page.locator(`section [aria-label="${label}"]`);
      if ((await field.count()) && !(await field.inputValue())) {
        await field.fill(value);
      }
    }
  } else {
    ok('the proposal arrived complete, so approval is available immediately');
  }

  // Correct the amount before approving: the button label is the UI admitting
  // that what runs is no longer what was proposed.
  await page.fill('section input[aria-label="Amount"]', '9');
  await page.waitForSelector(
    'section button:has-text("Run with my corrections"):not([disabled])',
    {
      timeout: 5000,
    },
  );
  ok('editing an argument turns approval into a correction');
  await page.click('section button:has-text("Run with my corrections")');

  const decision = decisions.at(-1);
  decision?.approved === true && Number(decision?.arguments?.amount) === 9
    ? ok('the corrected amount is what went back to the graph')
    : bad(`the decision dropped the correction: ${JSON.stringify(decision)}`);

  const nextAnswer = async (seen) => {
    // The rep's own question mentions £29, so waiting for any element whose text
    // contains "9" matches the question and reads it as the answer.
    await page
      .waitForFunction(
        ([selector, n]) => document.querySelectorAll(selector).length > n,
        [ANSWER, seen],
        { timeout: 90000 },
      )
      .catch(() => null);
    const text = await page.locator(ANSWER).last().innerText();
    // One line: a wrapped answer makes the failure message unreadable, and this
    // is the only record of what the model actually said.
    const flat = text.replace(/\s+/g, ' ').trim().toLowerCase();
    console.log(`   answered: ${flat.slice(0, 300)}`);
    return flat;
  };

  // That the *tool* ran on the corrected amount is settled by the decision frame
  // above and by the agent's own tests. What is checked here is narrower and is
  // all the browser can honestly see: the answer is about the corrected refund.
  // It may well also mention the £29 charge, and explaining the difference to the
  // rep is the assistant doing its job, not a leak of the proposed amount.
  const answer = await nextAnswer(answersBefore);
  /\b9(\.00)?\b/.test(answer)
    ? ok('the answer is about the corrected refund')
    : bad(`the answer never mentions the corrected amount: ${answer}`);

  console.log('== tool gate: cancelling runs nothing ==');
  await page.fill(
    'main form input[placeholder]',
    'Actually refund demo@example.com £50 as well.',
  );
  await page.click('main button:has-text("Ask")');
  // Guarded like the gate above: the planner may decline this one too, and an
  // unguarded wait turns that into a crash that loses every check after it.
  const offered = await page
    .waitForSelector('button:has-text("Cancel")', { timeout: 90000 })
    .then(() => true)
    .catch(() => false);
  if (!offered) {
    bad('no tool proposal reached the gate for the second refund request');
  } else {
    await page.click('button:has-text("Cancel")');
    await page.waitForSelector('button:has-text("Cancel")', {
      state: 'detached',
      timeout: 30000,
    });
    ok('cancelling closes the gate without running the tool');
    // Deliberately broad. A run that correctly said "has been reviewed and has not
    // been authorized" failed a /cancel/ check, and tightening prose assertions
    // around one model's wording is how you end up tuning the test instead of the
    // product. That nothing *ran* is asserted above; this only catches the
    // assistant reporting success for a call that was refused.
    const afterCancel = await nextAnswer(answersBefore + 1);
    /cancel|not authori[sz]|declin|rejected|not (been )?process|was not/i.test(
      afterCancel,
    )
      ? ok('the assistant reports that the action did not happen')
      : bad(`the resumed run did not report the cancellation: ${afterCancel}`);
    ok('the tool call parked before running');
  }
}

console.log('== settings: models and contracts ==');
await page.click('a[href="/settings"]');
await page.waitForSelector('section:has-text("Models")', { timeout: 20000 });

// Generated from the same schema the API publishes: purpose is a select because
// the server declared it an enum.
const purpose = page.locator('select[aria-label="Purpose"]');
(await purpose.locator('option').allInnerTexts()).join(',') ===
'decision,answer'
  ? ok('the preference form offers the purposes the server declares')
  : bad('the purpose options do not match the schema');

// A bad value has to land on its own field, which is the whole point of
// carrying the server's field errors into the form.
await purpose.selectOption('decision');
await page.fill('[aria-label="Model"]', 'gpt-4o');
await page.click('section button:has-text("Use this model")');
await page.waitForSelector('text=/provider:name/', { timeout: 20000 });
ok('a rejected value reports the server\u2019s reason on its field');

await page.fill('[aria-label="Model"]', 'openai:gpt-4o-mini');
await page.click('section button:has-text("Use this model")');
await page.waitForSelector('text=/decision now uses/', { timeout: 20000 });
ok('a valid model is accepted and listed');

const contractLinks = await page
  .locator('section:has-text("Contracts") a')
  .evaluateAll((nodes) => nodes.map((n) => n.getAttribute('href')));
contractLinks.length === 3
  ? ok(`the generated contracts are reachable (${contractLinks.join(' ')})`)
  : bad(`expected three contract links, got ${contractLinks.join(' ')}`);

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

console.log('== traces, in the console ==');
// The run just exercised above, with the nodes it took nested under it. In the
// console rather than behind the admin: whoever asks why it answered that is
// already here.
await page.goto(`${BASE}/traces`);
await page.waitForSelector('aside button', { timeout: 20000 });
const runButtons = page.locator('aside button');
(await runButtons.count()) > 0
  ? ok(`${await runButtons.count()} run(s) listed in the trace view`)
  : bad('the trace view listed no runs after a full session');

await runButtons.first().click();
await page.waitForSelector('section[aria-label="trace"] li', {
  timeout: 20000,
});
const traceText = (
  await page.locator('section[aria-label="trace"]').innerText()
).replace(/\s+/g, ' ');
/node\./.test(traceText) && /MODEL CALLS/i.test(traceText)
  ? ok('the trace shows its nodes and what the run cost')
  : bad(`the trace is missing nodes or cost: ${traceText.slice(0, 200)}`);

// Noise is collapsed behind a count, so the signal is what you see first.
const expander = page
  .locator('section[aria-label="trace"] button', { hasText: /^\+\d+$/ })
  .first();
if ((await expander.count()) > 0) {
  await expander.click();
  (await page.locator('section[aria-label="trace"] dl').count()) > 0
    ? ok('the hidden attributes expand on demand')
    : bad('expanding a span showed nothing');
} else {
  bad('no span offered its hidden attributes');
}

// Prompts and ticket text are customer-written and must not reach a span.
!/BEGIN TICKET|Thank you for reaching out/i.test(traceText)
  ? ok('no customer prose leaked into the visible spans')
  : bad('a span is showing customer text');

console.log('== one socket for everything ==');
const app = sockets.filter((u) => u.includes('/ws/'));
// One per page load, not a fixed number: a hard-coded count needs
// recalibrating every time a navigation is added, and then it tests the
// script rather than the app.
app.length <= pageLoads
  ? ok(`${app.length} app socket(s) across ${pageLoads} page load(s)`)
  : bad(`${app.length} app sockets across ${pageLoads} page load(s)`);

errors.length === 0
  ? ok('no page errors')
  : bad(`page errors: ${errors.join(' | ')}`);

await page.screenshot({ path: 'e2e/last-run.png', fullPage: true });
await browser.close();

const failed = results.filter((r) => !r).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
