import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const m = setTimeout(() => {}, 0); for (let i = 0; i <= m; i++) { try { clearInterval(i); clearTimeout(i); } catch(_){} }
  const cards = document.querySelectorAll('.ts-card');
  cards.forEach((c, i) => c.classList.toggle('ts-active', i === 0));
});
await page.waitForTimeout(400);

// Test A: remove strip ::before only
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.tactical-strip::before { display: none !important; }`;
  s.id = 'test-no-before';
  document.head.appendChild(s);
});
await page.waitForTimeout(200);
await page.screenshot({ path: '/tmp/no_before.png', clip: { x: 0, y: 90, width: 700, height: 100 } });

// Test B: also remove isolation
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.tactical-strip { isolation: auto !important; overflow: visible !important; }`;
  s.id = 'test-no-iso';
  document.head.appendChild(s);
});
await page.waitForTimeout(200);
await page.screenshot({ path: '/tmp/no_iso.png', clip: { x: 0, y: 90, width: 700, height: 100 } });

// Test C: reset: original + only remove ts-wrap z-index
await page.evaluate(() => {
  document.getElementById('test-no-before')?.remove();
  document.getElementById('test-no-iso')?.remove();
  const s = document.createElement('style');
  s.textContent = `.ts-wrap { z-index: 1000 !important; } .ts-card { z-index: 1001 !important; } .ts-card * { z-index: 1002 !important; }`;
  s.id = 'test-zi';
  document.head.appendChild(s);
});
await page.waitForTimeout(200);
await page.screenshot({ path: '/tmp/z_bump.png', clip: { x: 0, y: 90, width: 700, height: 100 } });

// Test D: reset, force cards to RELATIVE instead of absolute
await page.evaluate(() => {
  document.getElementById('test-zi')?.remove();
  const s = document.createElement('style');
  s.textContent = `.ts-card { position: relative !important; inset: auto !important; opacity: 1 !important; transform: none !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(200);
await page.screenshot({ path: '/tmp/relative_card.png', clip: { x: 0, y: 90, width: 700, height: 400 } });

await browser.close();
