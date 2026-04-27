import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });

const snap = async () => page.evaluate(() => {
  const active = document.querySelector('.ts-card.ts-active');
  const all = [...document.querySelectorAll('.ts-card')];
  return {
    activeIdx: all.indexOf(active),
    activeOpacity: active ? getComputedStyle(active).opacity : null,
    activeTransform: active ? getComputedStyle(active).transform : null,
    allOpacities: all.map(c => getComputedStyle(c).opacity),
  };
});

for (const t of [100, 500, 1000, 2000, 3000, 5000, 8000, 11000, 15000]) {
  await page.waitForTimeout(t === 100 ? 100 : t - (t === 500 ? 100 : (t - 1000 + 1)));
}
// simpler: just log each time
console.log('--- reset ---');
await browser.close();

const browser2 = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx2 = await browser2.newContext({ viewport: { width: 1440, height: 900 } });
const p2 = await ctx2.newPage();
await p2.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });

const stops = [200, 800, 1500, 3000, 4500, 6000, 8000, 12000, 16000];
let prev = 0;
for (const stop of stops) {
  await p2.waitForTimeout(stop - prev);
  prev = stop;
  const s = await p2.evaluate(() => {
    const a = document.querySelector('.ts-card.ts-active');
    return a ? {
      op: getComputedStyle(a).opacity,
      tx: getComputedStyle(a).transform,
      idx: [...document.querySelectorAll('.ts-card')].indexOf(a),
    } : null;
  });
  console.log(`t=${stop}ms`, JSON.stringify(s));
}
await browser2.close();
