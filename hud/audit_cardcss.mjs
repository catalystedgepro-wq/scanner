import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Kill inactive cards first
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.ts-card:not(.ts-active) { display: none !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/c1_hide_inactive.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Additionally remove transition on card
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.ts-card { transition: none !important; transform: none !important; opacity: 1 !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/c2_no_trans.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Additionally set card position to static
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.ts-card { position: static !important; inset: auto !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/c3_static.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Check if .ts-rail has overflow:hidden clipping
await page.evaluate(() => {
  const s = document.createElement('style');
  s.textContent = `.ts-rail { overflow: visible !important; display: block !important; }`;
  document.head.appendChild(s);
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/c4_rail_visible.png', clip: { x: 0, y: 90, width: 1440, height: 150 } });

// Check computed styles at this point
const st = await page.evaluate(() => {
  const c = document.querySelector('.ts-card.ts-active');
  const h = c.querySelector('.ts-headline');
  return {
    card: { display: getComputedStyle(c).display, position: getComputedStyle(c).position, width: getComputedStyle(c).width, height: getComputedStyle(c).height, color: getComputedStyle(c).color },
    headline: { display: getComputedStyle(h).display, rect: (r=>({x:r.x,y:r.y,w:r.width,h:r.height}))(h.getBoundingClientRect()), text: h.textContent, color: getComputedStyle(h).color }
  };
});
console.log(JSON.stringify(st, null, 2));

await browser.close();
