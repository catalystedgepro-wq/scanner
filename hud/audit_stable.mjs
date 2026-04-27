import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });

// Disable the interval so the card stays stable for screenshot
await page.waitForTimeout(1500);
await page.evaluate(() => {
  // Kill any setInterval running on tactical strip
  const highest = setTimeout(() => {}, 0);
  for (let i = 0; i <= highest; i++) {
    try { clearInterval(i); clearTimeout(i); } catch (_) {}
  }
  // Ensure card 0 is active
  const cards = document.querySelectorAll('.ts-card');
  cards.forEach((c, i) => c.classList.toggle('ts-active', i === 0));
});
await page.waitForTimeout(800);

const snap = await page.evaluate(() => {
  const a = document.querySelector('.ts-card.ts-active');
  return a ? {
    op: getComputedStyle(a).opacity,
    tx: getComputedStyle(a).transform,
    text: a.innerText.slice(0, 80),
  } : null;
});
console.log('active state after freeze:', JSON.stringify(snap));

await page.screenshot({ path: '/tmp/strip_stable_wide.png', clip: { x: 0, y: 50, width: 1440, height: 200 } });
await page.screenshot({ path: '/tmp/strip_stable_zoom.png', clip: { x: 0, y: 95, width: 800, height: 95 } });
await browser.close();
