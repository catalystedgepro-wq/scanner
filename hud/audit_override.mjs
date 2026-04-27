import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const m = setTimeout(() => {}, 0); for (let i = 0; i <= m; i++) { try { clearInterval(i); clearTimeout(i); } catch(_){} }
});

// Override: force active card to red bg, huge white text
await page.evaluate(() => {
  const style = document.createElement('style');
  style.textContent = `
    .tactical-strip { background: red !important; }
    .tactical-strip::before, .tactical-strip::after { display: none !important; }
    .ts-card.ts-active { background: yellow !important; border: 3px solid red !important; color: black !important; }
    .ts-card.ts-active * { color: black !important; font-size: 20px !important; opacity: 1 !important; visibility: visible !important; display: inline-block !important; background: white !important; }
    .scanner-posture-bg, .scanner-posture-vignette { display: none !important; }
  `;
  document.head.appendChild(style);
});
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/override.png', clip: { x: 0, y: 50, width: 1440, height: 200 } });
await browser.close();
