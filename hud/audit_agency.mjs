import { chromium } from 'playwright';
const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('https://catalystedge.agency/?cb=' + Date.now(), { waitUntil: 'load', timeout: 45000 });
await page.waitForTimeout(3000);
const facts = await page.evaluate(() => ({
  hero_h1: document.querySelector('.hero h1')?.textContent,
  hero_badge: document.querySelector('.hero-badge')?.textContent,
  suite_cards: document.querySelectorAll('.suite-card').length,
  live_cards: document.querySelectorAll('.live-card').length,
  lc_sector: document.getElementById('lc-sector')?.textContent,
  lc_sector_sub: document.getElementById('lc-sector-sub')?.textContent,
  lc_target: document.getElementById('lc-target')?.textContent,
  lc_target_sub: document.getElementById('lc-target-sub')?.textContent,
  lc_signals: document.getElementById('lc-signals')?.textContent,
  lc_signals_sub: document.getElementById('lc-signals-sub')?.textContent,
  has_video: !!document.querySelector('.video-wrapper'),
}));
console.log(JSON.stringify(facts, null, 2));
await page.screenshot({ path: '/tmp/agency_top.png', fullPage: false });
await page.evaluate(() => window.scrollTo(0, 700));
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/agency_live.png', fullPage: false });
await page.evaluate(() => window.scrollTo(0, 1400));
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/agency_suite.png', fullPage: false });
await browser.close();
