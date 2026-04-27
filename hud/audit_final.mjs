import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2500);

const pre = await page.evaluate(() => {
  const cards = [...document.querySelectorAll('.ts-card')];
  return cards.map((c, i) => ({
    i, active: c.classList.contains('ts-active'),
    opacity: getComputedStyle(c).opacity,
    transform: getComputedStyle(c).transform,
  }));
});
console.log('BEFORE:', JSON.stringify(pre, null, 2));

await page.screenshot({ path: '/tmp/final_strip.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

await browser.close();
