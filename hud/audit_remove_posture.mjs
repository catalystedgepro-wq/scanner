import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Test 1: remove scanner-posture-bg entirely
await page.evaluate(() => {
  document.querySelector('.scanner-posture-bg')?.remove();
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/no_posture.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Test 2: also restore posture but lift strip z-index
await page.evaluate(() => {
  location.reload();
});
await page.waitForLoadState('load');
await page.waitForTimeout(2000);
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.tactical-strip { z-index: 100 !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/strip_zbump.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

await browser.close();
