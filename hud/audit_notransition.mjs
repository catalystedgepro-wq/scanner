import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Kill transition and transform on card
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `
    .ts-card { transition: none !important; transform: none !important; }
    .ts-card.ts-active { transform: none !important; }
  `;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/no_transition.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Kill opacity
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.ts-card { opacity: 1 !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/no_opacity.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Kill ALL position/display tricks - set card as static block flow
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `
    .ts-rail { display: block !important; overflow: visible !important; }
    .ts-card { position: static !important; display: block !important; opacity: 1 !important; transform: none !important; }
    .ts-card:not(.ts-active) { display: none !important; }
  `;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/block_card.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

await browser.close();
