import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Nuclear: remove ALL card/ts-* styles and apply trivial flex
await page.evaluate(() => {
  const nukeStyle = document.createElement('style');
  nukeStyle.textContent = `
    .ts-rail { display: block !important; overflow: visible !important; }
    .ts-card { all: revert !important; display: block !important; padding: 10px !important; border: 2px solid red !important; background: white !important; color: black !important; position: static !important; opacity: 1 !important; }
    .ts-card.ts-active { border-color: lime !important; }
    .ts-card:not(.ts-active) { display: none !important; }
    .ts-icon, .ts-body, .ts-label, .ts-headline, .ts-detail, .ts-arrow { all: revert !important; color: black !important; display: inline-block !important; background: yellow !important; padding: 2px !important; margin: 2px !important; }
  `;
  document.head.appendChild(nukeStyle);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/nuclear.png', clip: { x: 0, y: 80, width: 1440, height: 250 } });

await browser.close();
