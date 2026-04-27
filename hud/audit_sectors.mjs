import { chromium } from 'playwright';
const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/sectors/?cb=' + Date.now(), { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(3500);
const stats = await page.evaluate(() => ({
  sectors: document.getElementById('s-sectors')?.textContent,
  picks: document.getElementById('s-picks')?.textContent,
  coverage: document.getElementById('s-coverage')?.textContent,
  top_score: document.getElementById('s-top-score')?.textContent,
  leader: document.querySelector('.leader h3')?.textContent,
  leader_ticker: document.querySelector('.leader .lr-ticker')?.childNodes?.[0]?.textContent,
  card_count: document.querySelectorAll('.heat-cell').length,
  quiet_count: document.querySelectorAll('.quiet').length,
}));
console.log(JSON.stringify(stats, null, 2));
await page.screenshot({ path: '/tmp/sectors_top.png', fullPage: false });
await page.evaluate(() => window.scrollTo(0, 800));
await page.waitForTimeout(300);
await page.screenshot({ path: '/tmp/sectors_mid.png', fullPage: false });
await browser.close();
