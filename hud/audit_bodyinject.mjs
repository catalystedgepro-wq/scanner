import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const m = setTimeout(() => {}, 0); for (let i = 0; i <= m; i++) { try { clearInterval(i); clearTimeout(i); } catch(_){} }
});

await page.evaluate(() => {
  // 1: direct child of body, fixed position
  const a = document.createElement('div');
  a.textContent = 'BODY FIXED @ (320,127)';
  a.style.cssText = 'position:fixed;left:320px;top:127px;z-index:999999;color:red;font:700 22px sans-serif;background:yellow;padding:6px;';
  document.body.appendChild(a);

  // 2: direct child of body, static flow
  const b = document.createElement('div');
  b.textContent = 'BODY NORMAL FLOW BLOCK';
  b.style.cssText = 'color:lime;font:900 30px sans-serif;background:black;padding:12px;border:4px solid red;margin:20px;';
  document.body.insertBefore(b, document.body.firstChild);
});
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/body_inject.png', clip: { x: 0, y: 0, width: 1440, height: 300 } });

// Sample actual pixel at fixed canary (320,127) via canvas
const pixel = await page.evaluate(async () => {
  // We can't use canvas to sample viewport directly, but we can fetch rect
  const a = [...document.querySelectorAll('div')].find(d => d.textContent === 'BODY FIXED @ (320,127)');
  if (!a) return null;
  const r = a.getBoundingClientRect();
  return { top: r.top, left: r.left, w: r.width, h: r.height };
});
console.log('fixed canary rect:', JSON.stringify(pixel));

await browser.close();
