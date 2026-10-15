import { test, expect, Page } from '@playwright/test';

const chat = (page: Page) => page.locator('.ghost-chat-panel');
async function ask(page: Page, text: string) {
  const input = page.getByRole('textbox', { name: 'Message input' });
  if (!(await input.isVisible())) await page.getByRole('button', { name: 'Open Ghost Cursor chat' }).click();
  await input.fill(text);
  await input.press('Enter');
}
const approve = (page: Page) => page.getByRole('button', { name: 'Approve and Run' }).click();

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
  await expect(chat(page)).toContainText('executed successfully', { timeout: 20_000 });
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
  await expect(chat(page)).toContainText('executed successfully', { timeout: 30_000 });
});

test('dark mode', async ({ page }) => {
  await page.goto('/');
  await ask(page, 'Turn on dark mode');
  await approve(page);
  await expect(page.locator('[data-ghost-id="theme.dark"]')).toHaveClass(/bg-blue-50/, { timeout: 20_000 });
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

