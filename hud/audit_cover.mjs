import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Full elementsFromPoint sweep on the card region
const sweep = await page.evaluate(() => {
  const pts = [];
  // Scan x=100 to x=1200 at y=135 (card vertical center)
  for (let x = 100; x <= 1200; x += 100) {
    const els = document.elementsFromPoint(x, 135).slice(0, 6);
    pts.push({ x, stack: els.map(e => e.tagName + '.' + (e.className || '').toString().slice(0, 30)) });
  }

  // Also check fixed/absolute elements anywhere on page that could overlap strip
  const candidates = [];
  document.querySelectorAll('*').forEach(el => {
    const s = getComputedStyle(el);
    if (s.position === 'fixed' || s.position === 'absolute') {
      const r = el.getBoundingClientRect();
      // Does it overlap the strip (y=97 to y=190)?
      if (r.top < 190 && r.bottom > 97 && r.left < 1440 && r.right > 0 && r.width > 0 && r.height > 0) {
        // Skip strip itself and its descendants
        if (!el.closest('.tactical-strip')) {
          candidates.push({
            tag: el.tagName + '.' + (el.className || '').toString().slice(0, 40),
            rect: { x: r.x, y: r.y, w: r.width, h: r.height },
            position: s.position,
            zIndex: s.zIndex,
            bg: s.backgroundColor,
          });
        }
      }
    }
  });

  return { sweep: pts, overlappers: candidates };
});

console.log('SWEEP AT Y=135:');
console.log(JSON.stringify(sweep.sweep, null, 2));
console.log('\nOVERLAPPERS (external elements in strip area):');
console.log(JSON.stringify(sweep.overlappers, null, 2));

await browser.close();
