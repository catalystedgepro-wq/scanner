import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);

// Find ALL elements whose bounding rect intersects the strip (y=96 to y=189)
const overlaps = await page.evaluate(() => {
  const all = [...document.querySelectorAll('*')];
  const STRIP_TOP = 96, STRIP_BOT = 190;
  const results = [];
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.height === 0 || r.width === 0) continue;
    if (r.top > STRIP_BOT || r.bottom < STRIP_TOP) continue;
    // Overlaps the strip area
    const s = getComputedStyle(el);
    // Filter to things that could be painting — skip descendants of .tactical-strip
    const inStrip = el.closest('.tactical-strip');
    if (inStrip && el !== inStrip) continue;
    results.push({
      tag: el.tagName + (el.id ? '#'+el.id : '') + (el.className ? '.'+String(el.className).replace(/\s+/g,'.').slice(0,60) : ''),
      rect: { top: r.top, left: r.left, w: r.width, h: r.height },
      zIndex: s.zIndex,
      position: s.position,
      background: s.backgroundColor,
      pointerEvents: s.pointerEvents,
      display: s.display,
      opacity: s.opacity,
    });
  }
  return results.slice(0, 30);
});

console.log(JSON.stringify(overlaps, null, 2));
await browser.close();
