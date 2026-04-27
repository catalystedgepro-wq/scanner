import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'networkidle', timeout: 45000 });
await page.waitForTimeout(1500);

// Screenshot just the strip + nav at high resolution
await page.screenshot({
  path: '/tmp/strip_hires.png',
  clip: { x: 0, y: 40, width: 1440, height: 170 },
});

// Take two snapshots 3s apart to see card rotation
await page.screenshot({
  path: '/tmp/strip_t0.png',
  clip: { x: 0, y: 90, width: 1440, height: 100 },
});
await page.waitForTimeout(5500);
await page.screenshot({
  path: '/tmp/strip_t1.png',
  clip: { x: 0, y: 90, width: 1440, height: 100 },
});

await browser.close();
console.log('done');
