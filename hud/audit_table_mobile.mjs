import { chromium } from 'playwright';
const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/?cb=' + Date.now(), { waitUntil: 'load', timeout: 60000 });
await page.waitForTimeout(3000);
const result = await page.evaluate(() => {
  const wraps = [...document.querySelectorAll('.tbl-wrap')];
  const bodyOverflow = window.getComputedStyle(document.body).overflowX;
  const docScroll = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  const tbl = wraps.map((w,i) => {
    const cs = window.getComputedStyle(w);
    const t = w.querySelector('table');
    return {
      idx: i,
      overflowX: cs.overflowX,
      scrollable: t ? t.scrollWidth > w.clientWidth : false,
      wrapWidth: w.clientWidth,
      tableWidth: t ? t.scrollWidth : 0,
    };
  });
  return { bodyOverflowX: bodyOverflow, pageHorizontalOverflow: docScroll, wraps: tbl };
});
console.log(JSON.stringify(result, null, 2));
await page.screenshot({ path: '/tmp/scanner_mobile_tables.png', fullPage: false });
await page.evaluate(() => window.scrollTo(0, 2800));
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/scanner_mobile_tables2.png', fullPage: false });
await browser.close();
