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
await page.waitForTimeout(600);

// Zoom on just the left portion of the strip where icon + text should be
await page.screenshot({ path: '/tmp/orig_zoom.png', clip: { x: 0, y: 90, width: 700, height: 100 } });

// Also sample the pixel at (200, 128) where "10 gap plays" headline should render
const pix = await page.evaluate(async () => {
  // Draw page to canvas and read pixel
  const canvas = document.createElement('canvas');
  canvas.width = 1440; canvas.height = 900;
  // Can't draw viewport to canvas directly, but we can inspect offsetParent chain
  const active = document.querySelector('.ts-card.ts-active');
  const hdr = active?.querySelector('.ts-headline');
  const lbl = active?.querySelector('.ts-label');
  return {
    activeClasses: active?.className,
    hdrText: hdr?.textContent,
    hdrColor: hdr && getComputedStyle(hdr).color,
    lblText: lbl?.textContent,
    lblColor: lbl && getComputedStyle(lbl).color,
  };
});
console.log(JSON.stringify(pix));

await browser.close();
