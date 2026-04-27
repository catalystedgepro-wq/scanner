import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const m = setTimeout(() => {}, 0); for (let i = 0; i <= m; i++) { try { clearInterval(i); clearTimeout(i); } catch(_){} }
});

await page.evaluate(() => {
  const strip = document.querySelector('.tactical-strip');
  const rail = document.querySelector('.ts-rail');

  // Canary INSIDE the rail, simple big text, huge contrast
  const t = document.createElement('div');
  t.id = 'CANARY-TEST';
  t.textContent = 'HELLO INSIDE RAIL';
  t.style.cssText = 'position:absolute;top:30px;left:200px;z-index:99999;background:magenta;color:white;font:900 30px sans-serif;padding:8px;';
  rail.appendChild(t);

  // Also do screenshot-time zIndex dump
  const stack = [];
  const nodes = document.querySelectorAll('.tactical-strip, .tactical-strip *');
  nodes.forEach(n => {
    const s = getComputedStyle(n);
    if (s.position !== 'static') {
      stack.push({ tag: n.tagName+'.'+(n.className||'').toString().slice(0,40), pos: s.position, z: s.zIndex });
    }
  });
  window.__STACK = stack;
});
await page.waitForTimeout(400);

const stack = await page.evaluate(() => window.__STACK);
console.log('POSITIONED ELEMENTS IN STRIP:');
console.log(JSON.stringify(stack, null, 2));

await page.screenshot({ path: '/tmp/canary2.png', clip: { x: 0, y: 80, width: 900, height: 150 } });
await browser.close();
