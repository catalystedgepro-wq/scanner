import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

const result = await page.evaluate(() => {
  const card = document.querySelector('.ts-card.ts-active');
  const body = card.querySelector('.ts-body');
  const headline = card.querySelector('.ts-headline');

  // Position inside the 90px card
  const mk = (parent, label, leftPx) => {
    const p = document.createElement('span');
    p.textContent = label;
    p.style.cssText = `position:absolute;left:${leftPx}px;top:20px;background:red;color:white;padding:4px;font:900 14px sans-serif;z-index:999999;`;
    parent.appendChild(p);
    return p;
  };

  const p1 = mk(card, 'ON-CARD', 200);
  const p2 = mk(body, 'ON-BODY', 350);
  const p3 = mk(headline, 'ON-HEAD', 500);

  const r1 = p1.getBoundingClientRect();
  const r2 = p2.getBoundingClientRect();
  const r3 = p3.getBoundingClientRect();
  const stack = (x, y) => document.elementsFromPoint(x, y).map(e => e.tagName + '.' + (e.className || '').toString().slice(0, 40));
  return {
    p1: { rect: {x: r1.x, y: r1.y, w: r1.width, h: r1.height}, stack: stack(r1.x + 5, r1.y + 5) },
    p2: { rect: {x: r2.x, y: r2.y, w: r2.width, h: r2.height}, stack: stack(r2.x + 5, r2.y + 5) },
    p3: { rect: {x: r3.x, y: r3.y, w: r3.width, h: r3.height}, stack: stack(r3.x + 5, r3.y + 5) },
  };
});

console.log(JSON.stringify(result, null, 2));
await page.screenshot({ path: '/tmp/layer2.png', clip: { x: 0, y: 90, width: 1000, height: 100 } });
await browser.close();
