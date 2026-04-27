import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

// Insert probe at each level and check elementsFromPoint at the probe location
const result = await page.evaluate(() => {
  const card = document.querySelector('.ts-card.ts-active');
  const body = card.querySelector('.ts-body');
  const headline = card.querySelector('.ts-headline');

  const mk = (parent, label, y) => {
    const p = document.createElement('span');
    p.textContent = label;
    p.style.cssText = `position:absolute;left:${parent === card ? 250 : parent === body ? 350 : 450}px;top:${y}px;background:red;color:white;padding:4px;font:900 14px sans-serif;z-index:999999;`;
    parent.appendChild(p);
    return p;
  };

  const p1 = mk(card, 'ON-CARD', 110);
  const p2 = mk(body, 'ON-BODY', 110);
  const p3 = mk(headline, 'ON-HEADLINE', 110);

  // What's the elementsFromPoint at each?
  const r1 = p1.getBoundingClientRect();
  const r2 = p2.getBoundingClientRect();
  const r3 = p3.getBoundingClientRect();

  const stack = (x, y) => document.elementsFromPoint(x, y).map(e => e.tagName + '.' + (e.className || '').toString().slice(0, 40));

  return {
    p1: { rect: {x: r1.x, y: r1.y, w: r1.width, h: r1.height}, stack: stack(r1.x + r1.width/2, r1.y + r1.height/2) },
    p2: { rect: {x: r2.x, y: r2.y, w: r2.width, h: r2.height}, stack: stack(r2.x + r2.width/2, r2.y + r2.height/2) },
    p3: { rect: {x: r3.x, y: r3.y, w: r3.width, h: r3.height}, stack: stack(r3.x + r3.width/2, r3.y + r3.height/2) },
  };
});

console.log(JSON.stringify(result, null, 2));
await page.screenshot({ path: '/tmp/layer.png', clip: { x: 0, y: 90, width: 900, height: 100 } });
await browser.close();
