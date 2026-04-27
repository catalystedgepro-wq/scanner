import { chromium } from 'playwright';
import { readFileSync } from 'fs';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

await page.evaluate(() => {
  const card = document.querySelector('.ts-card.ts-active');
  const p = document.createElement('span');
  p.id = 'PIXEL-PROBE';
  p.textContent = 'XXX';
  p.style.cssText = 'position:absolute;left:200px;top:20px;background:red;color:yellow;padding:4px;font:900 20px sans-serif;z-index:999999;display:block;width:100px;height:40px;';
  card.appendChild(p);
});
await page.waitForTimeout(200);

await page.screenshot({ path: '/tmp/pixel_full.png' });

const r = await page.evaluate(() => {
  const p = document.getElementById('PIXEL-PROBE');
  const r = p.getBoundingClientRect();
  // Force a repaint
  p.offsetHeight;
  return { x: r.x, y: r.y, w: r.width, h: r.height, computedBg: getComputedStyle(p).backgroundColor };
});
console.log('probe rect:', JSON.stringify(r));

// Check actual pixel at probe location using canvas capture
await browser.close();

// Now analyze the pixel in the full screenshot
const img = readFileSync('/tmp/pixel_full.png');
// Parse PNG header to get width
const w = img.readUInt32BE(16);
const h = img.readUInt32BE(20);
console.log(`screenshot: ${w}x${h}`);
