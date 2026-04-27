import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const m = setTimeout(() => {}, 0); for (let i = 0; i <= m; i++) { try { clearInterval(i); clearTimeout(i); } catch(_){} }
  const cards = document.querySelectorAll('.ts-card');
  cards.forEach((c, i) => c.classList.toggle('ts-active', i === 0));
});
await page.waitForTimeout(500);

// Full viewport of the strip + 50px above + 50px below
await page.screenshot({ path: '/tmp/full_strip.png', clip: { x: 0, y: 50, width: 1440, height: 250 } });

// Walk the chain and find any filter/clip-path/blend
const chain = await page.evaluate(() => {
  const h = document.querySelector('.ts-card.ts-active .ts-headline');
  const out = [];
  let el = h;
  while (el && el !== document.documentElement) {
    const s = getComputedStyle(el);
    out.push({
      tag: el.tagName + (el.className ? '.' + el.className.toString().slice(0,60) : ''),
      opacity: s.opacity,
      visibility: s.visibility,
      display: s.display,
      filter: s.filter,
      backdropFilter: s.backdropFilter,
      mixBlendMode: s.mixBlendMode,
      clipPath: s.clipPath,
      mask: s.mask,
      maskImage: s.maskImage,
      transform: s.transform,
      pointerEvents: s.pointerEvents,
      color: s.color,
      position: s.position,
      zIndex: s.zIndex,
      overflow: s.overflow,
    });
    el = el.parentElement;
  }
  return out;
});
console.log(JSON.stringify(chain, null, 2));

await browser.close();
