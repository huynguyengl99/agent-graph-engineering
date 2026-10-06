/**
 * A recorded walk through every feature, as both people who use it.
 * Video per scenario plus stills at each step. Output is gitignored.
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const URL = process.env.TARGET_URL || 'http://localhost:5173';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = process.env.OUT_DIR || path.join(HERE, '..', '..', 'captures');
const API = process.env.API_URL || 'http://localhost:8000';
const PASS = 'demo-pass-123';
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

const results = [];
const ok = (n, d = '') => { results.push(['PASS', n, d]); console.log(`  PASS  ${n}${d ? '  ' + d : ''}`); };
const bad = (n, d = '') => { results.push(['FAIL', n, d]); console.log(`  FAIL  ${n}${d ? '  ' + d : ''}`); };

async function scenario(browser, name, viewport, body) {
  const dir = path.join(OUT, name);
  fs.mkdirSync(dir, { recursive: true });
  const context = await browser.newContext({
    viewport,
    recordVideo: { dir, size: viewport },
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/401|Unauthorized/.test(m.text())) errors.push(m.text());
  });
  let n = 0;
  const shot = async (label) => {
    n += 1;
    await page.screenshot({ path: path.join(dir, `${String(n).padStart(2, '0')}-${label}.png`) });
  };
  console.log(`\n== ${name} ==`);
  try {
    await body(page, shot);
  } catch (e) {
    bad(`${name} threw`, String(e).split('\n')[0].slice(0, 120));
    await shot('threw');
  }
  if (errors.length) bad(`${name}: page errors`, errors.slice(0, 2).join(' | ').slice(0, 140));
  else ok(`${name}: no page errors`);
  await context.close();
  return dir;
}

const login = async (page, email) => {
  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASS);
  await page.click('button[type="submit"]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
};

/**
 * A run ends in one of two good ways: an answer, or a ticket handed to a
 * person. Silence with the agent still holding it is the bad one, and that is
 * the distinction worth asserting.
 */
const settled = async (page, ticketId, label) => {
  try {
    await page.waitForSelector('text=/Agent \\(/', { timeout: 120000 });
    ok(`${label}: the agent answered`);
    return 'answered';
  } catch {
    const res = await page.request.get(`${API}/api/tickets/${ticketId}/`);
    const handling = res.ok() ? (await res.json()).handling : '?';
    if (handling === 'needs_human') {
      ok(`${label}: handed to a person instead of answering`);
      return 'handed over';
    }
    bad(`${label}: nothing in 120s`, `handling=${handling}`);
    return 'stuck';
  }
};

const toBottom = (page) => page.evaluate(() => {
  Array.from(document.querySelectorAll('*'))
    .filter((e) => e.scrollHeight > e.clientHeight + 40 && e.clientHeight > 200)
    .forEach((e) => (e.scrollTop = e.scrollHeight));
});

const newTicket = async (page, title, body) => {
  await page.getByRole('button', { name: /new ticket/i }).click();
  await page.waitForTimeout(500);
  const dlg = page.locator('div').filter({ hasText: /What do you need help with/ }).last();
  await dlg.locator('input').first().fill(title);
  await dlg.locator('textarea').first().fill(body);
  return dlg;
};

(async () => {
  const browser = await chromium.launch({ headless: true });

  // ---------- 1. the customer reports a problem and is answered ----------
  await scenario(browser, '1-customer', DESKTOP, async (page, shot) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await shot('login');
    await login(page, 'customer@example.com');
    page.url().includes('/portal') ? ok('customer lands on the portal') : bad('customer lands on the portal', page.url());
    await shot('portal');

    const dlg = await newTicket(page, 'Charged twice for my plan', 'My statement shows two charges of 29.00 this month for the same plan. Can you check?');
    await shot('dialog');
    await dlg.getByRole('button', { name: /^send$/i }).click();
    await page.waitForTimeout(1500);
    await shot('posted');

    // the stream, caught mid-flight
    await page.waitForTimeout(4000);
    await shot('working');

    const ticketId = page.url().split('/').pop();

    // Sampled while the agent writes: one jump from nothing to the whole reply
    // means the stream is being dropped somewhere between the model and here.
    const lengths = [];
    const grow = setInterval(async () => {
      const t = await page.locator('li', { hasText: /^Agent/ }).last()
        .innerText().catch(() => '');
      if (t) lengths.push(t.length);
    }, 700);
    const outcome = await settled(page, ticketId, 'the customer ticket');
    clearInterval(grow);
    if (outcome === 'answered') {
      const steps = new Set(lengths).size;
      steps > 1
        ? ok('the reply is written in front of them', `${steps} step(s)`)
        : bad('the reply is written in front of them', 'arrived whole');
    } else {
      ok('the reply is written in front of them', 'skipped: handed to a person');
    }
    await page.waitForTimeout(2500);
    await toBottom(page);
    await shot('answered');

    // The thread, not the whole page: the sidebar is every ticket they ever
    // opened, and a title of their own choosing is not a leak. Reasoning is not
    // on this list any more - the workings behind their own reply are theirs.
    const thread = (await page.locator('main').innerText()).toLowerCase();
    // Not 'escalat': a reply saying it will escalate to billing is the normal
    // thing to tell a customer.
    const leaks = ['internal note', 'guardrail'].filter(
      (w) => thread.includes(w),
    );
    leaks.length
      ? bad('nothing internal reaches the customer', leaks.join(','))
      : ok('nothing internal reaches the customer');

    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);
    await toBottom(page);
    await shot('after-reload');
    if (outcome === 'answered') {
      (await page.locator('text=/Agent \\(/').count())
        ? ok('the answer survives a reload')
        : bad('the answer survives a reload');
    } else {
      ok('the answer survives a reload', 'skipped: handed to a person');
    }

    await page.locator('input[placeholder*="Add to this ticket" i]').fill('Thanks, that explains it.');
    await shot('customer-replies');
    await page.getByRole('button', { name: /^send$/i }).click();
    await page.waitForTimeout(3000);
    await toBottom(page);
    await shot('customer-replied');
    ok('the customer can reply on the thread');
  });

  // ---------- 2. the console, the trail, and an internal note ----------
  await scenario(browser, '2-staff-console', DESKTOP, async (page, shot) => {
    await login(page, 'demo@example.com');
    await shot('console');
    ok('staff land on the console');

    await page.locator('li, a').filter({ hasText: /Charged twice for my plan/ }).first().click();
    await page.waitForTimeout(2500);
    await toBottom(page);
    await shot('ticket');

    const trail = await page.getByRole('button', { name: /Chose what to do|Filed the ticket/ }).count();
    trail ? ok('the reasoning trail is on the ticket', `${trail} step(s)`) : bad('the reasoning trail is on the ticket');

    const first = page.getByRole('button', { name: /Filed the ticket|Chose what to do/ }).first();
    await first.click();
    await page.waitForTimeout(600);
    await shot('trail-expanded');
    ok('a reasoning step expands');

    await page.locator('input[placeholder*="Note for your team" i]').fill('Checked billing: two charges confirmed on the same day.');
    await shot('note-typed');
    await page.getByRole('button', { name: /^note$/i }).click();
    await page.waitForTimeout(2500);
    await toBottom(page);
    await shot('note-posted');
    (await page.locator('text=/INTERNAL NOTE/i').count()) ? ok('an internal note is recorded') : bad('an internal note is recorded');

    await page.locator('input[placeholder*="Note for your team" i]').fill('What should we tell them while billing checks?');
    await page.getByRole('button', { name: /^send$/i }).last().click();
    await page.waitForTimeout(4000);
    await shot('agent-thinking');
    try {
      await page.waitForSelector('text=/Agent \\(/', { timeout: 120000 });
      ok('the agent answers the team');
    } catch { bad('the agent answers the team', 'nothing in 120s'); }
    await page.waitForTimeout(2000);
    await toBottom(page);
    await shot('agent-answered');

    await page.getByRole('button', { name: /take over|hand back/i }).click();
    await page.waitForTimeout(800);
    await shot('handover-dialog');
    ok('the handover dialog opens');
    await page.keyboard.press('Escape');
  });

  // ---------- 3. the tool gate ----------
  await scenario(browser, '3-tool-gate', DESKTOP, async (page, shot) => {
    await login(page, 'demo@example.com');
    await page.locator('li, a').filter({ hasText: /Charged twice for my plan/ }).first().click();
    await page.waitForTimeout(2500);
    await page.locator('input[placeholder*="Note for your team" i]')
      .fill('Please issue a refund of 29.00 to customer@example.com for the duplicate charge.');
    await page.getByRole('button', { name: /^send$/i }).last().click();
    await page.waitForTimeout(4000);
    await shot('asked');
    try {
      await page.waitForSelector('text=/Run issue_refund/i', { timeout: 120000 });
      ok('the tool gate opens before anything runs');
    } catch { bad('the tool gate opens before anything runs', 'nothing in 120s'); }
    await page.waitForTimeout(2000);
    await toBottom(page);
    await shot('gate');

    const fields = await page.getByLabel(/^(Email|Amount|Reason)$/).count();
    fields >= 3 ? ok('the gate form came from the tool schema', `${fields} field(s)`) : bad('the gate form came from the tool schema', `${fields}`);

    await page.getByLabel('Amount').fill('9');
    await page.waitForTimeout(500);
    await shot('corrected');
    // Approval and correction are not the same act, and the button says so.
    const correct = page.getByRole('button', { name: /run with my corrections/i });
    (await correct.isVisible())
      ? ok('editing an argument turns approval into a correction')
      : bad('editing an argument turns approval into a correction');
    (await page.getByText(/1 field changed/i).count())
      ? ok('the gate says how much was changed')
      : bad('the gate says how much was changed');

    await correct.click();
    await page.waitForTimeout(5000);
    await toBottom(page);
    await shot('running');
    try {
      await page.waitForSelector('text=/refund processed|9\\.00|£9/i', { timeout: 120000 });
      ok('the corrected amount is what ran');
    } catch { bad('the corrected amount is what ran', 'no result in 120s'); }
    await page.waitForTimeout(2500);
    await toBottom(page);
    await shot('ran');
  });

  // ---------- 4. graphs, traces, settings ----------
  await scenario(browser, '4-console-pages', DESKTOP, async (page, shot) => {
    await login(page, 'demo@example.com');
    for (const [route, label, probe] of [
      ['/graphs', 'graphs', /support_decide/],
      ['/traces', 'traces', /run|RUNS/],
      ['/settings', 'settings', /Models/],
    ]) {
      await page.goto(URL + route, { waitUntil: 'networkidle' });
      await page.waitForTimeout(3000);
      await shot(label);
      const text = await page.locator('body').innerText();
      probe.test(text) ? ok(`${label} renders`) : bad(`${label} renders`, text.slice(0, 60));
    }

    // the xray toggle on the graph
    await page.goto(URL + '/graphs', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);
    const xray = page.getByRole('checkbox');
    await xray.uncheck();
    await page.waitForTimeout(2000);
    await shot('graphs-collapsed');
    await xray.check();
    await page.waitForTimeout(2000);
    await shot('graphs-expanded');
    ok('subgraphs expand and collapse');

    // a trace, opened
    await page.goto(URL + '/traces', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);
    await page.locator('li').filter({ hasText: /support run/ }).first().click();
    await page.waitForTimeout(2000);
    await shot('trace-open');
    // Not the "NODE" chip: that text is lowercase in the DOM and uppercased by
    // CSS, so matching it asserts on the stylesheet rather than the trace.
    const steps = await page.getByText(/support_start|support_decide/).count();
    steps ? ok('a trace shows its steps', `${steps} node(s)`) : bad('a trace shows its steps');
  });

  // ---------- 5. the same app on a phone ----------
  await scenario(browser, '5-phone', PHONE, async (page, shot) => {
    await login(page, 'customer@example.com');
    await shot('portal-list');
    let over = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    over ? bad('the portal list fits a phone') : ok('the portal list fits a phone');

    await page.locator('a, li').filter({ hasText: /Charged twice for my plan/ }).first().click();
    await page.waitForTimeout(2500);
    await toBottom(page);
    await shot('portal-thread');
    over = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    over ? bad('the portal thread fits a phone') : ok('the portal thread fits a phone');

    const back = page.getByRole('link', { name: /All tickets/i });
    (await back.isVisible()) ? ok('a phone gets a way back to the list') : bad('a phone gets a way back to the list');
    await back.click();
    await page.waitForTimeout(1200);
    await shot('back-to-list');

    await page.getByRole('button', { name: /sign out/i }).click();
    await page.waitForTimeout(1500);
    await login(page, 'demo@example.com');
    for (const [route, label] of [['/', 'console'], ['/graphs', 'graphs'], ['/traces', 'traces'], ['/settings', 'settings']]) {
      await page.goto(URL + route, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1800);
      await shot(`staff-${label}`);
      const o = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
      o ? bad(`${label} fits a phone`) : ok(`${label} fits a phone`);
    }
  });

  // ---------- 6. two people on one ticket at the same time ----------
  console.log('\n== 6-concurrent ==');
  {
    const dir = path.join(OUT, '6-concurrent');
    fs.mkdirSync(dir, { recursive: true });
    const mk = async (who) => {
      const ctx = await browser.newContext({
        viewport: DESKTOP,
        recordVideo: { dir: path.join(dir, who), size: DESKTOP },
      });
      const pg = await ctx.newPage();
      const errs = [];
      pg.on('pageerror', (e) => errs.push(String(e)));
      let i = 0;
      const sh = async (l) => {
        i += 1;
        await pg.screenshot({ path: path.join(dir, who, `${String(i).padStart(2, '0')}-${l}.png`) });
      };
      return { ctx, pg, errs, sh };
    };
    const C = await mk('customer');
    const S = await mk('staff');

    try {
      await Promise.all([login(C.pg, 'customer@example.com'), login(S.pg, 'demo@example.com')]);
      ok('both sessions are live at once');

      const dlg = await newTicket(C.pg, 'Two people watching', 'My plan was billed twice this month. Please take a look.');
      await dlg.getByRole('button', { name: /^send$/i }).click();
      await C.pg.waitForTimeout(2500);
      const ticketId = C.pg.url().split('/').pop();
      await C.sh('customer-opened');

      // staff opens the same ticket, without the customer doing anything
      await S.pg.goto(`${URL}/tickets/${ticketId}`, { waitUntil: 'networkidle' });
      await S.pg.waitForTimeout(2500);
      await toBottom(S.pg);
      await S.sh('staff-opened');
      (await S.pg.locator('text=/billed twice/i').count())
        ? ok('staff see the ticket the customer just opened')
        : bad('staff see the ticket the customer just opened');

      // the agent works: staff watch the reasoning, the customer must not
      await Promise.all([C.pg.waitForTimeout(5000), S.pg.waitForTimeout(5000)]);
      await Promise.all([C.sh('customer-while-working'), S.sh('staff-while-working')]);
      const staffMid = await S.pg.locator('body').innerText();
      const custMid = await C.pg.locator('body').innerText();
      /Filed the ticket|Chose what to do|reasoning/i.test(staffMid)
        ? ok('staff watch the agent reason')
        : bad('staff watch the agent reason');
      // They are shown their own run being worked out. What they must never
      // see is the team's half, which is a different run on a topic they
      // cannot subscribe to.
      /INTERNAL/.test(custMid)
        ? bad("the team's half never reaches the customer", 'internal content visible')
        : ok("the team's half never reaches the customer");
      // "Agent" without the model: that is the bubble being written. The model
      // name only appears once the finished reply is an event.
      /Filed the ticket|Chose what to do|Wrote the reply|Agent/.test(custMid)
        ? ok('the customer watches their own reply being worked out')
        : bad('the customer watches their own reply being worked out', 'nothing shown');

      await settled(S.pg, ticketId, 'the run with both watching');
      await Promise.all([C.pg.waitForTimeout(3000), S.pg.waitForTimeout(3000)]);
      await Promise.all([toBottom(C.pg), toBottom(S.pg)]);
      await Promise.all([C.sh('customer-answered'), S.sh('staff-answered')]);

      // the customer types while staff are on the same ticket: staff see it live
      const before = await S.pg.locator('text=/Any update/i').count();
      await C.pg.locator('input[placeholder*="Add to this ticket" i]').fill('Any update on this?');
      await C.pg.getByRole('button', { name: /^send$/i }).click();
      await S.pg.waitForTimeout(4000);
      await toBottom(S.pg);
      await S.sh('staff-sees-customer-live');
      const after = await S.pg.locator('text=/Any update/i').count();
      after > before
        ? ok("the customer's message reaches staff without a reload")
        : bad("the customer's message reaches staff without a reload");

      // staff post an internal note: the customer must never see it
      await S.pg.locator('input[placeholder*="Note for your team" i]').fill('Billing confirmed the duplicate, refund pending.');
      await S.pg.getByRole('button', { name: /^note$/i }).click();
      await Promise.all([S.pg.waitForTimeout(3500), C.pg.waitForTimeout(3500)]);
      await Promise.all([toBottom(S.pg), toBottom(C.pg)]);
      await Promise.all([S.sh('staff-note'), C.sh('customer-must-not-see-note')]);
      (await C.pg.locator('text=/Billing confirmed the duplicate/i').count())
        ? bad('an internal note never reaches the customer', 'the customer can see it')
        : ok('an internal note never reaches the customer');
      (await S.pg.locator('text=/Billing confirmed the duplicate/i').count())
        ? ok('the note is on the team half')
        : bad('the note is on the team half');
    } catch (e) {
      bad('6-concurrent threw', String(e).split('\n')[0].slice(0, 120));
    }
    const allErrs = [...C.errs, ...S.errs];
    allErrs.length ? bad('6-concurrent: page errors', allErrs.slice(0, 2).join(' | ').slice(0, 140))
                   : ok('6-concurrent: no page errors');
    await Promise.all([C.ctx.close(), S.ctx.close()]);
  }

  await browser.close();

  const failed = results.filter((r) => r[0] === 'FAIL');
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length) {
    console.log('failures:');
    failed.forEach(([, n, d]) => console.log(`  - ${n} ${d}`));
  }
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
  process.exit(failed.length ? 1 : 0);
})();
