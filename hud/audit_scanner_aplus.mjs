import { chromium } from 'playwright';
const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1800 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/?cb=' + Date.now(), { waitUntil: 'load', timeout: 60000 });
await page.waitForTimeout(3500);
const facts = await page.evaluate(() => {
  const bodyText = document.body.innerText;
  const h1s = [...document.querySelectorAll('h1')];
  const proofNums = [...document.querySelectorAll('.shp-num')].map(n => n.textContent.trim());
  const proofLabels = [...document.querySelectorAll('.shp-label')].map(n => n.textContent.trim());
  return {
    h1Count: h1s.length,
    h1Text: h1s.map(h => h.textContent.trim()),
    hasScannerHero: !!document.querySelector('.scanner-hero'),
    hasProofStrip: !!document.querySelector('.sh-proof'),
    proofNums,
    proofLabels,
    hasUnknownLeak: /top:\s*\w+\s*·\s*unknown/i.test(bodyText),
    hasZeroConfirmedBuys: /0 confirmed buys/i.test(bodyText),
    tableScrollCount: document.querySelectorAll('.table-scroll').length,
  };
});
console.log(JSON.stringify(facts, null, 2));
await page.screenshot({ path: '/tmp/scanner_aplus_top.png', fullPage: false });
// Mobile audit
await page.setViewportSize({ width: 390, height: 1800 });
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/scanner_aplus_mobile.png', fullPage: false });
const mobileFacts = await page.evaluate(() => {
  const proof = document.querySelector('.sh-proof');
  const cs = proof ? window.getComputedStyle(proof).gridTemplateColumns : null;
  return { proofGridColsMobile: cs };
});
console.log('MOBILE:', JSON.stringify(mobileFacts, null, 2));
await browser.close();
