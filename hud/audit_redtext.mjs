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
  // ONLY force text colors — nothing else
  const s = document.createElement('style');
  s.textContent = `
    .ts-card.ts-active .ts-headline,
    .ts-card.ts-active .ts-label,
    .ts-card.ts-active .ts-detail,
    .ts-card.ts-active .ts-arrow,
    .ts-cta-label,
    .ts-cta-sub {
      color: red !important;
      font-size: 20px !important;
      font-weight: 900 !important;
      text-shadow: 0 0 2px white !important;
    }
  `;
  document.head.appendChild(s);
});
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/redtext.png', clip: { x: 0, y: 80, width: 1440, height: 130 } });
await browser.close();
