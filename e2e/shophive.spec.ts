import { test, expect, type Page } from '@playwright/test';

const chat = (page: Page) => page.locator('.ghost-chat-panel');
async function ask(page: Page, text: string) {
  const input = page.getByRole('textbox', { name: 'Message input' });
  if (!(await input.isVisible())) await page.getByRole('button', { name: 'Open Ghost Cursor chat' }).click();
  await input.fill(text);
  await input.press('Enter');
}
const approve = (page: Page) => page.getByRole('button', { name: 'Approve and Run' }).click();

/** Records the overlay cursor's state, transform and opacity on every animation frame. */
async function sampleCursor(page: Page) {
  await page.evaluate(() => {
    const w = window as any;
    w.__gcSamples = [];
    const tick = () => {
      const host = document.getElementById('ghost-cursor-overlay');
      const cur = host?.shadowRoot?.querySelector('.gc-main') as HTMLElement | null;
      if (host && cur) {
        const cs = getComputedStyle(cur);
        let hit: string | null = null;
        const m = /matrix\(([^)]+)\)/.exec(cs.transform);
        if (m) {
          const n = m[1].split(',').map(Number);
          const under = document.elementFromPoint(n[4] + 1.34, n[5] + 1.34);
          hit = under?.closest('[data-ghost-id]')?.getAttribute('data-ghost-id')
            ?? (under?.closest('#ghost-cursor-widget-container') ? 'WIDGET' : null);
        }
        w.__gcSamples.push({ state: host.getAttribute('data-gc-cursor-state'), transform: cs.transform, opacity: cs.opacity, hit });
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}
type CursorSample = { state: string; transform: string; opacity: string; hit: string | null };
const cursorSamples = (page: Page): Promise<CursorSample[]> => page.evaluate(() => (window as any).__gcSamples);

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  const btn = page.getByRole('button', { name: 'Sign in (demo)' });
  if (await btn.isVisible()) {
    await btn.click();
    await expect(page.getByText('Hi, demo')).toBeVisible();
  }
});

test('widget is mounted', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Open Ghost Cursor chat' })).toBeVisible();
});

test('add to cart waits for approval, then changes React state', async ({ page }) => {
  await page.goto('/');
  await ask(page, 'Add the Air Max 90 in size 10 to my cart');
  await expect(page.getByRole('button', { name: 'Approve and Run' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Cart (0)' })).toBeVisible();
  await approve(page);
  await expect(page).toHaveURL(/\/product\/air-max-90$/);
  await expect(page.getByRole('link', { name: 'Cart (1)' })).toBeVisible({ timeout: 20_000 });
  await expect(chat(page)).toContainText('Added the Air Max 90', { timeout: 20_000 });
});

test('order lookup uses the private backend tool', async ({ page }) => {
  await page.goto('/orders');
  await ask(page, 'Where is my order SH-1024?');
  await expect(chat(page)).toContainText('1Z999AA10123456784', { timeout: 20_000 });
});

test('checkout asks for the address, then fills the form', async ({ page }) => {
  await page.goto('/cart');
  await ask(page, 'I want to checkout');
  await page.getByRole('button', { name: '123 Main St, NYC (saved)' }).click();
  await approve(page);
  await expect(page.locator('[data-ghost-id="checkout.zip"]')).toHaveValue('10001', { timeout: 20_000 });
  await expect(page.locator('[data-ghost-id="checkout.state"]')).toHaveValue('NY');
});

test('tracking question runs a tour on the orders page', async ({ page }) => {
  await page.goto('/');
  await ask(page, 'How do I track my order?');
  await approve(page);
  await expect(page).toHaveURL(/\/orders$/);

  // Step 1: Click Next
  const nextBtn = page.locator('#ghost-tour-next');
  await expect(nextBtn).toBeVisible({ timeout: 10_000 });
  await expect(nextBtn).toHaveText('Next');
  await nextBtn.click();

  // Step 2: Click Next
  await expect(page.getByText('Step 2 of 3')).toBeVisible({ timeout: 10_000 });
  await nextBtn.click();

  // Step 3: Click Finish
  await expect(page.getByText('Step 3 of 3')).toBeVisible({ timeout: 10_000 });
  await expect(nextBtn).toHaveText('Finish');
  await nextBtn.click();

  await expect(chat(page)).toContainText('track an order', { timeout: 30_000 });
});

test('dark mode', async ({ page }) => {
  await page.goto('/');
  await ask(page, 'Turn on dark mode');
  await approve(page);
  await expect(page.locator('[data-ghost-id="theme.toggle"]')).toBeChecked({ timeout: 20_000 });
  await expect(page.locator('html')).toHaveClass(/dark/);
  // The body background has a 0.3 s transition, so poll until it settles.
  await expect
    .poll(() => page.evaluate(() => getComputedStyle(document.body).backgroundColor))
    .toBe('rgb(3, 7, 18)');
  expect(await page.evaluate(() => getComputedStyle(document.querySelector('section')!).borderTopColor)).toBe('rgb(55, 65, 81)');
  await expect(chat(page)).toContainText('Theme switched to Dark Mode', { timeout: 20_000 });
});

test('browser only talks to its own gateway and gets a public envelope', async ({ page }) => {
  const hosts = new Set<string>();
  const bodies: any[] = [];
  page.on('request', r => hosts.add(new URL(r.url()).host));
  page.on('response', async r => {
    if (r.request().method() === 'POST' && r.url().endsWith('/api/ghost-cursor')) bodies.push(await r.json());
  });
  await page.goto('/');
  await ask(page, 'Where is my order SH-1024?');
  await expect(chat(page)).toContainText('UPS', { timeout: 20_000 });
  expect([...hosts]).toEqual(['127.0.0.1:8081']);
  for (const b of bodies) {
    expect(Object.keys(b).sort()).toEqual(['actions', 'protocolVersion', 'questions', 'reply', 'revision', 'runId', 'status']);
    expect(JSON.stringify(b)).not.toContain('GHOST_BRAIN_SERVER_ONLY_CANARY_2026');
  }
});

test('unauthenticated POST to /api/ghost-cursor returns 401', async ({ playwright }) => {
  const req = await playwright.request.newContext();
  const res = await req.post('http://127.0.0.1:8081/api/ghost-cursor', {
    data: {
      command: 'start',
      protocolVersion: '1',
      requestId: 'test-req',
      message: 'Hi',
      context: { page: 'home', values: {}, availableTargets: [] },
    },
  });
  expect(res.status()).toBe(401);
});

test('typing card number on checkout does not leak to context.values or targets', async ({ page }) => {
  const requests: any[] = [];
  page.on('request', r => {
    if (r.method() === 'POST' && r.url().endsWith('/api/ghost-cursor')) {
      try {
        requests.push(r.postDataJSON());
      } catch {}
    }
  });

  await page.goto('/checkout');
  await page.locator('input[name="cardNumber"]').fill('4111222233334444');
  await page.locator('input[name="expiry"]').fill('12/28');
  await page.locator('input[name="cvv"]').fill('123');

  await ask(page, 'Help with checkout');
  await expect(chat(page)).toBeVisible({ timeout: 20_000 });

  expect(requests.length).toBeGreaterThan(0);
  for (const req of requests) {
    const raw = JSON.stringify(req);
    expect(raw).not.toContain('4111222233334444');
    expect(raw).not.toContain('checkout.card_number');
    expect(raw).not.toContain('checkout.cvv');

    const availableTargets = req.context?.availableTargets || [];
    for (const target of availableTargets) {
      expect(target).not.toContain('cardNumber');
      expect(target).not.toContain('card_number');
      expect(target).not.toContain('cvv');
    }
  }
});

test('typing ZIP code on checkout sends fresh context value', async ({ page }) => {
  const requests: any[] = [];
  page.on('request', r => {
    if (r.method() === 'POST' && r.url().endsWith('/api/ghost-cursor')) {
      try {
        requests.push(r.postDataJSON());
      } catch {}
    }
  });

  await page.goto('/checkout');
  await page.locator('[data-ghost-id="checkout.zip"]').fill('94105');

  await ask(page, 'Help with checkout');
  await expect(chat(page)).toBeVisible({ timeout: 20_000 });

  expect(requests.length).toBeGreaterThan(0);
  expect(requests[0].context?.values?.['checkout.zip']).toBe('94105');
});

test('target registry enforces allowed operations and resolves via registered resolve()', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async () => {
    const sdk = (window as any).__GHOST_CURSOR_SDK__;
    sdk.clearTargetRegistry();

    let clicked = false;
    const testEl = document.createElement('button');
    testEl.id = 'registered-button-test';
    testEl.textContent = 'Registered Click Test';
    testEl.style.width = '120px';
    testEl.style.height = '40px';
    testEl.onclick = () => { clicked = true; };
    document.body.appendChild(testEl);

    sdk.registerTarget('custom_btn', {
      page: 'home',
      resolve: () => document.getElementById('registered-button-test'),
      operations: ['click'],
    });

    const executor = new sdk.ActionExecutor({ timeout: 500 });

    // 1. Trying fill_input on click-only target
    const fillRes = await executor.execute([
      { id: '1', type: 'fill_input', target_id: 'custom_btn', value: 'hello' },
    ]);

    // 2. Trying click on click-only target
    const clickRes = await executor.execute([
      { id: '2', type: 'click', target_id: 'custom_btn' },
    ]);

    document.body.removeChild(testEl);
    return { fillRes, clickRes, clicked };
  });

  expect(result.fillRes.success).toBe(false);
  expect(result.fillRes.results[0].error).toBe('operation not allowed');
  expect(result.clickRes.success).toBe(true);
  expect(result.clickRes.results[0].ok).toBe(true);
  expect(result.clicked).toBe(true);
});

test('semantic text lookup is disabled by default and only works when opted in', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async () => {
    const sdk = (window as any).__GHOST_CURSOR_SDK__;
    sdk.clearTargetRegistry();

    const btn = document.createElement('button');
    btn.textContent = 'UniqueSemanticButtonText';
    document.body.appendChild(btn);

    // Default resolution: semantic lookup should be false
    const defaultRes = await sdk.resolveTargetWithCascade('UniqueSemanticButtonText', { timeout: 300 });

    // Opt-in resolution: semantic lookup enabled
    const optInRes = await sdk.resolveTargetWithCascade('UniqueSemanticButtonText', {
      timeout: 300,
      allowSemanticLookup: true,
    });

    document.body.removeChild(btn);
    return {
      defaultMatched: defaultRes.matched,
      optInMatched: optInRes.matched,
      optInLevel: optInRes.level,
    };
  });

  expect(result.defaultMatched).toBe(false);
  expect(result.optInMatched).toBe(true);
  expect(result.optInLevel).toBe(5);
});

test('invalid target_id formats are rejected with error invalid target id', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async () => {
    const sdk = (window as any).__GHOST_CURSOR_SDK__;
    const executor = new sdk.ActionExecutor();

    const resSpace = await executor.execute([
      { id: '1', type: 'click', target_id: 'bad id with space' },
    ]);

    const resSpecial = await executor.execute([
      { id: '2', type: 'fill_input', target_id: 'bad#id$!', value: 'test' },
    ]);

    return {
      spaceError: resSpace.results[0]?.error,
      specialError: resSpecial.results[0]?.error,
    };
  });

  expect(result.spaceError).toBe('invalid target id');
  expect(result.specialError).toBe('invalid target id');
});


test('new message clears previous approval panel and prevents running stale plan', async ({ page }) => {
  await page.goto('/');
  // 1. Ask "Turn on dark mode" and don't approve
  await ask(page, 'Turn on dark mode');
  await expect(page.getByRole('button', { name: 'Approve and Run' })).toBeVisible({ timeout: 10_000 });

  // 2. Ask "What sizes are available?". The approval panel disappears.
  await ask(page, 'What sizes are available?');
  await expect(page.getByRole('button', { name: 'Approve and Run' })).not.toBeVisible();
  await expect(chat(page)).toContainText('sizes 7 through 13', { timeout: 20_000 });

  // 3. Ask "Turn on dark mode" again and approve. It still works.
  await ask(page, 'Turn on dark mode');
  await expect(page.getByRole('button', { name: 'Approve and Run' })).toBeVisible({ timeout: 10_000 });
  await approve(page);
  await expect(page.locator('[data-ghost-id="theme.toggle"]')).toBeChecked({ timeout: 20_000 });
});

test('cancel button cancels the plan and notifies server', async ({ page }) => {
  const cancelRequests: any[] = [];
  page.on('request', r => {
    if (r.method() === 'POST' && r.url().endsWith('/api/ghost-cursor')) {
      try {
        const body = r.postDataJSON();
        if (body.kind === 'cancel') cancelRequests.push(body);
      } catch {}
    }
  });

  await page.goto('/');
  await ask(page, 'Turn on dark mode');
  await expect(page.getByRole('button', { name: 'Approve and Run' })).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(page.getByRole('button', { name: 'Approve and Run' })).not.toBeVisible();
  await expect(chat(page)).toContainText('Plan cancelled.', { timeout: 10_000 });
  expect(cancelRequests.length).toBe(1);
  expect(cancelRequests[0].kind).toBe('cancel');
});

test('accessibility: role=log, aria-live=polite, focus on open, and escape to close', async ({ page }) => {
  await page.goto('/');
  const openBtn = page.getByRole('button', { name: 'Open Ghost Cursor chat' });
  await expect(openBtn).toBeVisible();
  await openBtn.click();

  // Check role=log and aria-live=polite
  const logEl = page.locator('[role="log"][aria-live="polite"]');
  await expect(logEl).toBeVisible();

  // Focus on input
  const input = page.getByRole('textbox', { name: 'Message input' });
  await expect(input).toBeFocused();

  // Escape key closes chat
  await page.keyboard.press('Escape');
  await expect(chat(page)).not.toBeVisible();

  // Can reopen
  await openBtn.click();
  await expect(chat(page)).toBeVisible();
});

test('tour renders HTML as literal text and prevents XSS (S-13)', async ({ page }) => {
  await page.goto('/orders');
  const trackBtn = page.locator('[data-ghost-id$=".track"]').first();
  await expect(trackBtn).toBeVisible({ timeout: 10_000 });
  const targetId = await trackBtn.getAttribute('data-ghost-id');
  expect(targetId).toBeTruthy();

  void page.evaluate((tid) => {
    const sdk = (window as any).__GHOST_CURSOR_SDK__;
    new sdk.ActionExecutor().execute([
      {
        id: 'a1',
        type: 'guided_tour',
        steps: [
          {
            target_id: tid,
            message: '<img src=x onerror="window.__xss=1">Track here',
          },
        ],
      },
    ]);
  }, targetId);

  const nextBtn = page.locator('#ghost-tour-next');
  await expect(nextBtn).toBeVisible({ timeout: 10_000 });

  const xssValue = await page.evaluate(() => (window as any).__xss);
  expect(xssValue).toBeUndefined();

  const tooltip = page.locator('#ghost-tour-tooltip');
  await expect(tooltip).toContainText('<img src=x');

  const skipBtn = page.locator('#ghost-tour-skip');
  await expect(skipBtn).toBeVisible();
  await skipBtn.click();
  await expect(tooltip).not.toBeVisible();
});

test('cursor flies out of the dock along a curve and docks again', async ({ page }) => {
  await page.goto('/');
  await sampleCursor(page);
  await ask(page, 'Turn on dark mode');
  await approve(page);
  await expect(page.locator('[data-ghost-id="theme.toggle"]')).toBeChecked({ timeout: 20_000 });
  await expect(page.locator('#ghost-cursor-overlay')).toHaveAttribute('data-gc-cursor-state', 'docked', { timeout: 10_000 });

  const samples = await cursorSamples(page);
  const flying = new Set(samples.filter(s => s.state === 'flying').map(s => s.transform));
  expect(flying.size).toBeGreaterThanOrEqual(12);
  expect(samples.some(s => s.state === 'returning')).toBe(true);
  expect(samples[samples.length - 1].opacity).toBe('0');
  await expect(page.locator('#ghost-cursor-canvas')).toHaveCount(0);
});

test('mission bar keeps the target visible while the cursor acts', async ({ page }) => {
  await page.goto('/');
  await sampleCursor(page);
  await ask(page, 'Turn on dark mode');
  await approve(page);
  await expect(page.locator('.ghost-chat-panel.gc-mission')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-ghost-id="theme.toggle"]')).toBeChecked({ timeout: 20_000 });
  await expect(page.locator('.ghost-chat-panel.gc-mission')).toHaveCount(0, { timeout: 10_000 });
  await expect(chat(page)).toContainText('Theme switched to Dark Mode', { timeout: 20_000 });

  const acting = (await cursorSamples(page)).filter(s => s.state === 'acting');
  expect(acting.length).toBeGreaterThan(0);
  expect(acting.some(s => s.hit === 'theme.toggle')).toBe(true);
  expect(acting.some(s => s.hit === 'WIDGET')).toBe(false);
});

test('Stop during a flight sends the cursor home within 400 ms, and the next plan still runs', async ({ page }) => {
  await page.goto('/');
  await ask(page, 'Add the Air Max 90 in size 10 to my cart');
  await approve(page);
  await expect(page.locator('#ghost-cursor-overlay')).toHaveAttribute('data-gc-cursor-state', 'flying', { timeout: 15_000 });
  await page.evaluate(() => {
    const w = window as any;
    const widgetRoot = document.getElementById('ghost-cursor-widget-container')!.shadowRoot!;
    widgetRoot.addEventListener('click', (e) => {
      const t = e.target as Element;
      if (t.closest && t.closest('[aria-label="Stop"]')) w.__stopAt = performance.now();
    }, true);
    const host = document.getElementById('ghost-cursor-overlay')!;
    new MutationObserver(() => {
      const s = host.getAttribute('data-gc-cursor-state');
      if (w.__stopAt && !w.__homeAt && (s === 'returning' || s === 'docked')) w.__homeAt = performance.now();
    }).observe(host, { attributes: true, attributeFilter: ['data-gc-cursor-state'] });
  });
  await page.getByRole('button', { name: 'Stop' }).click();
  await page.waitForFunction(() => (window as any).__homeAt, null, { timeout: 5_000 });
  const elapsed = await page.evaluate(() => (window as any).__homeAt - (window as any).__stopAt);
  expect(elapsed).toBeLessThan(400);
  await expect(chat(page)).toContainText('Stopped. Steps already done were kept.', { timeout: 10_000 });

  await ask(page, 'Turn on dark mode');
  await approve(page);
  await expect(page.locator('[data-ghost-id="theme.toggle"]')).toBeChecked({ timeout: 20_000 });
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' as any, contextOptions: { reducedMotion: 'reduce' } });

  test('the cursor fades between targets instead of flying', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await sampleCursor(page);
    await ask(page, 'Turn on dark mode');
    await approve(page);
    await expect(page.locator('[data-ghost-id="theme.toggle"]')).toBeChecked({ timeout: 20_000 });
    await expect(page.locator('#ghost-cursor-overlay')).toHaveAttribute('data-gc-cursor-state', 'docked', { timeout: 10_000 });
    const flying = new Set((await cursorSamples(page)).filter(s => s.state === 'flying').map(s => s.transform));
    expect(flying.size).toBeLessThanOrEqual(3);
  });
});





