import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);

await page.evaluate(() => {
  const max = setTimeout(() => {}, 0);
  for (let i = 0; i <= max; i++) { try { clearInterval(i); clearTimeout(i); } catch (_) {} }
});

// Inject a test div in the strip's wrap at z-index 9999
await page.evaluate(() => {
  const wrap = document.querySelector('.tactical-strip .ts-wrap');
  const div = document.createElement('div');
  div.textContent = 'CANARY TEST TEXT 123';
  div.style.cssText = 'position:absolute;left:300px;top:30px;z-index:9999;color:red;font:700 24px sans-serif;background:yellow;padding:4px;';
  wrap.appendChild(div);
});
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/canary.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Now inject text INSIDE the active card's ts-body
await page.evaluate(() => {
  const body = document.querySelector('.ts-card.ts-active .ts-body');
  const div = document.createElement('div');
  div.textContent = 'INSIDE BODY — should show';
  div.style.cssText = 'color:red;font:700 20px sans-serif;background:yellow;padding:2px;';
  body.appendChild(div);
});
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/canary_inside.png', clip: { x: 0, y: 90, width: 1440, height: 100 } });

// Check pixel values at a known headline position using html2canvas-like approach
// Use Chrome's built-in: we'll examine computed values of parent container
const diag = await page.evaluate(() => {
  const strip = document.querySelector('.tactical-strip');
  const parent = strip?.parentElement;
  const grandparent = parent?.parentElement;
  const dump = (el, lab) => el ? ({
    lab, tag: el.tagName + (el.className ? '.' + String(el.className).slice(0,60) : ''),
    opacity: getComputedStyle(el).opacity,
    filter: getComputedStyle(el).filter,
    overflow: getComputedStyle(el).overflow,
    visibility: getComputedStyle(el).visibility,
    display: getComputedStyle(el).display,
    transform: getComputedStyle(el).transform,
    clipPath: getComputedStyle(el).clipPath,
    contains: getComputedStyle(el).contain,
  }) : null;
  return [dump(strip,'strip'), dump(parent,'parent'), dump(grandparent,'grand')];
});
console.log('parent chain:', JSON.stringify(diag, null, 2));

await browser.close();
