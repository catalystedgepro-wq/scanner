import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

await page.evaluate(() => {
  const card = document.querySelector('.ts-card.ts-active');
  const p = document.createElement('span');
  p.id = 'PIXEL-PROBE';
  p.textContent = 'PROBE';
  p.style.cssText = 'position:absolute;left:200px;top:20px;background:red;color:yellow;padding:4px;font:900 20px sans-serif;z-index:999999;';
  card.appendChild(p);
});
await page.waitForTimeout(300);

// Tight crop on just the probe location: x=236, y=117, w=100, h=40
await page.screenshot({ path: '/tmp/probe_tight.png', clip: { x: 200, y: 110, width: 200, height: 60 } });

await browser.close();
