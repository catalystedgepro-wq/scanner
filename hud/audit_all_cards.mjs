import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('http://localhost:8765/scanner/', { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(1500);

const labels = await page.evaluate(() => {
  const cards = Array.from(document.querySelectorAll('.ts-card'));
  return cards.map((c, i) => ({
    idx: i,
    label: c.querySelector('.ts-label')?.textContent || '',
    headline: c.querySelector('.ts-headline')?.textContent || '',
    detail: c.querySelector('.ts-detail')?.textContent || '',
    href: c.getAttribute('href'),
  }));
});
console.log(JSON.stringify(labels, null, 2));

// Screenshot cards 4 (Convergence) and 8 (Sympathy) for eyeballing
for (const i of [3, 4, 5, 6, 8, 9, 10]) {
  await page.evaluate((n) => {
    const cards = document.querySelectorAll('.ts-card');
    const dots = document.querySelectorAll('.ts-dot');
    cards.forEach((c, k) => c.classList.toggle('ts-active', k === n));
    dots.forEach((d, k) => d.classList.toggle('ts-dot-active', k === n));
  }, i);
  await page.waitForTimeout(400);
  await page.screenshot({ path: `/tmp/card_${i}.png`, clip: { x: 0, y: 85, width: 1440, height: 110 } });
}

await browser.close();
