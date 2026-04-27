import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(2000);

await page.evaluate(() => {
  const strip = document.querySelector('.tactical-strip');
  const wrap = document.querySelector('.ts-wrap');
  const rail = document.querySelector('.ts-rail');
  const card = document.querySelector('.ts-card.ts-active');

  const mk = (parent, label, top, bg) => {
    const p = document.createElement('div');
    p.textContent = label;
    p.style.cssText = `position:absolute;top:${top}px;left:50px;z-index:99999;background:${bg};color:black;font:900 12px sans-serif;padding:3px 6px;`;
    parent.appendChild(p);
  };

  mk(strip, 'IN-STRIP', 5, 'red');
  mk(wrap, 'IN-WRAP', 20, 'lime');
  mk(rail, 'IN-RAIL', 35, 'cyan');
  mk(card, 'IN-CARD', 50, 'yellow');
});
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/levels.png', clip: { x: 0, y: 90, width: 400, height: 110 } });
await browser.close();
