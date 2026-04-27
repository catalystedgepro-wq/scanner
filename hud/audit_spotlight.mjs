import { chromium } from 'playwright';
const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);
// Find spotlight element and scroll to it
const box = await page.evaluate(() => {
  const el = document.querySelector('.spotlight');
  if (!el) return null;
  el.scrollIntoView({ block: 'center' });
  const r = el.getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
console.log('spotlight box:', box);
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/spotlight.png', fullPage: false });
await browser.close();
