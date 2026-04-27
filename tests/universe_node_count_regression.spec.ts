import { test, expect, request } from '@playwright/test';

// Regression guard: HUD must show the full backend universe.
// Historical regression (2026-04-14): min_gravity=2 query param cut 10,870 → 2,166 visible.
// If this test fails, a client-side filter has been re-introduced.

const PROD = 'http://67.205.148.181';
const MIN_EXPECTED_NODES = 10000;

test('backend universe returns at least 10,000 nodes', async () => {
  const ctx = await request.newContext();
  const res = await ctx.get(`${PROD}/api/universe?per_page=500&page=1`);
  expect(res.ok()).toBeTruthy();
  const data = await res.json();
  expect(data.total).toBeGreaterThanOrEqual(MIN_EXPECTED_NODES);
});

test('HUD Visible Universe count matches backend total within 5%', async ({ page }) => {
  const ctx = await request.newContext();
  const apiRes = await ctx.get(`${PROD}/api/universe?per_page=500&page=1`);
  const apiData = await apiRes.json();
  const backendTotal: number = apiData.total;

  await page.goto(`${PROD}/hud/`);
  await page.waitForTimeout(8000);

  const visibleText = await page.locator('text=/\\d[\\d,]*\\s*\\/\\s*\\d[\\d,]*/').first().textContent({ timeout: 30000 });
  expect(visibleText).toBeTruthy();

  const match = visibleText!.match(/(\d[\d,]*)\s*\/\s*(\d[\d,]*)/);
  expect(match).toBeTruthy();
  const visible = parseInt(match![1].replace(/,/g, ''), 10);
  const total = parseInt(match![2].replace(/,/g, ''), 10);

  const delta = Math.abs(total - backendTotal) / backendTotal;
  expect(delta).toBeLessThan(0.05);
  expect(visible).toBeGreaterThanOrEqual(MIN_EXPECTED_NODES * 0.9);
});
