import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const m = setTimeout(() => {}, 0); for (let i = 0; i <= m; i++) { try { clearInterval(i); clearTimeout(i); } catch(_){} }
  const cards = document.querySelectorAll('.ts-card');
  cards.forEach((c, i) => c.classList.toggle('ts-active', i === 0));
});
await page.waitForTimeout(500);

const info = await page.evaluate(() => {
  const h = document.querySelector('.ts-card.ts-active .ts-headline');
  const l = document.querySelector('.ts-card.ts-active .ts-label');
  const card = document.querySelector('.ts-card.ts-active');
  const strip = document.querySelector('.tactical-strip');
  const getR = (el) => el ? (r => ({x:r.x,y:r.y,w:r.width,h:r.height}))(el.getBoundingClientRect()) : null;

  const pt = document.elementsFromPoint(400, 135).map(e => e.tagName + '.' + (e.className || '').toString().slice(0,40));
  return {
    strip: getR(strip),
    card: getR(card),
    headline: { rect: getR(h), text: h?.textContent, color: h && getComputedStyle(h).color },
    label: { rect: getR(l), text: l?.textContent, color: l && getComputedStyle(l).color },
    stackAt400_135: pt,
  };
});
console.log(JSON.stringify(info, null, 2));
await page.screenshot({ path: '/tmp/fix_audit.png', clip: { x: 0, y: 80, width: 1440, height: 130 } });
await browser.close();
