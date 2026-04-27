import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Inspect the active card's headline span: actual text nodes, fonts, char metrics
const detail = await page.evaluate(() => {
  const h = document.querySelector('.ts-card.ts-active .ts-headline');
  if (!h) return { err: 'no headline' };

  const s = getComputedStyle(h);
  const r = h.getBoundingClientRect();

  // What fonts actually loaded?
  const fonts = [...document.fonts].map(f => ({ family: f.family, status: f.status, weight: f.weight }));

  // Measure text
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  ctx.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
  const m = ctx.measureText(h.textContent || '');

  // Check if inline content renders — append a visible child
  const probe = document.createElement('span');
  probe.style.cssText = 'background: red; color: white; padding: 2px 4px; font-size: 14px;';
  probe.textContent = 'PROBE-IN-HEADLINE';
  h.appendChild(probe);
  const pr = probe.getBoundingClientRect();

  return {
    headline: {
      rect: { x: r.x, y: r.y, w: r.width, h: r.height },
      text: h.textContent,
      innerHTML: h.innerHTML.slice(0, 200),
      color: s.color,
      font: `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`,
      display: s.display,
      visibility: s.visibility,
      opacity: s.opacity,
      fillColor: s.webkitTextFillColor,
      textShadow: s.textShadow,
      fontSynthesis: s.fontSynthesis,
    },
    fontsLoaded: fonts,
    textMetrics: { width: m.width, actualBoundingBoxAscent: m.actualBoundingBoxAscent },
    probe: { rect: { x: pr.x, y: pr.y, w: pr.width, h: pr.height } },
  };
});
console.log(JSON.stringify(detail, null, 2));

await page.screenshot({ path: '/tmp/probe.png', clip: { x: 0, y: 90, width: 900, height: 100 } });
await browser.close();
