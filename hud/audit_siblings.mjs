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

// Inject TWO siblings: (1) as child of .tactical-strip, (2) as child of ts-wrap
await page.evaluate(() => {
  const strip = document.querySelector('.tactical-strip');
  const wrap = document.querySelector('.tactical-strip .ts-wrap');

  const a = document.createElement('div');
  a.id = 'canary-strip';
  a.textContent = 'SIBLING OF WRAP (inside strip)';
  a.style.cssText = 'position:absolute;top:10px;left:400px;z-index:99999;background:lime;color:black;font:900 22px sans-serif;padding:4px;';
  strip.appendChild(a);

  const b = document.createElement('div');
  b.id = 'canary-wrap';
  b.textContent = 'CHILD OF WRAP';
  b.style.cssText = 'position:absolute;top:50px;left:600px;z-index:99999;background:cyan;color:black;font:900 22px sans-serif;padding:4px;';
  wrap.appendChild(b);

  const c = document.createElement('div');
  c.id = 'canary-outside';
  c.textContent = 'AFTER strip (sibling)';
  c.style.cssText = 'position:absolute;top:97px;left:200px;z-index:99999;background:orange;color:black;font:900 22px sans-serif;padding:4px;';
  strip.insertAdjacentElement('afterend', c);
});
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/siblings.png', clip: { x: 0, y: 50, width: 1440, height: 200 } });
await browser.close();
