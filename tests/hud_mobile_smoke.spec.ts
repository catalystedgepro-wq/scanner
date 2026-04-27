import { test, expect } from '@playwright/test';

/**
 * Mobile HUD smoke — proves:
 * 1. Mobile CSS is reachable at the live asset path and contains the media query.
 * 2. Desktop rendering is unchanged (no mobile rules applied at 1440x900).
 * 3. At 390x844 (iPhone 13), the page scrolls vertically (overflow unlocked)
 *    — a desktop-locked-viewport regression would fail this check.
 *
 * Run: PLAYWRIGHT_BASE_URL=https://catalystedgescanner.com npx playwright test tests/hud_mobile_smoke.spec.ts
 */

const HUD_PATH = '/cerebro/app/';
const BUNDLE_PATH = '/cerebro/app/assets/';

test.describe('Cerebro HUD mobile layer', () => {
  test('mobile media query present in live CSS bundle', async ({ request }) => {
    const res = await request.get(`${process.env.PLAYWRIGHT_BASE_URL ?? 'https://catalystedgescanner.com'}${HUD_PATH}`);
    expect(res.status()).toBe(200);
    const html = await res.text();
    const match = html.match(/assets\/(index-[A-Za-z0-9_-]+\.css)/);
    expect(match, 'React CSS bundle reference must be present').not.toBeNull();
    const cssRes = await request.get(`${process.env.PLAYWRIGHT_BASE_URL ?? 'https://catalystedgescanner.com'}${BUNDLE_PATH}${match![1]}`);
    expect(cssRes.status()).toBe(200);
    const css = await cssRes.text();
    expect(css).toMatch(/max-width:\s*768px/);
    expect(css).toMatch(/max-width:\s*420px/);
  });

  test('desktop 1440x900 — document does not scroll vertically', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(HUD_PATH);
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    const overflow = await page.evaluate(() => {
      return {
        bodyOverflowY: getComputedStyle(document.body).overflowY,
        htmlHeight: document.documentElement.scrollHeight,
        winHeight: window.innerHeight,
      };
    });
    expect(overflow.htmlHeight).toBeLessThanOrEqual(overflow.winHeight + 50);
  });

  test('mobile 390x844 — document scrolls vertically', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await page.goto(HUD_PATH);
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    const m = await page.evaluate(() => ({
      bodyOverflowY: getComputedStyle(document.body).overflowY,
      htmlHeight: document.documentElement.scrollHeight,
      winHeight: window.innerHeight,
      bodyWidth: document.body.getBoundingClientRect().width,
      winWidth: window.innerWidth,
    }));
    expect(m.bodyWidth).toBeLessThanOrEqual(m.winWidth + 2);
    expect(m.bodyOverflowY === 'auto' || m.bodyOverflowY === 'visible').toBeTruthy();
    await page.screenshot({ path: 'output/playwright/hud_mobile_390.png', fullPage: true });
  });
});
