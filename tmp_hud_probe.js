const { chromium } = require('playwright');
(async()=>{
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 969 } });
  await page.goto('http://67.205.148.181/#hud', { waitUntil: 'networkidle' });
  await page.screenshot({ path: '/home/operator/.openclaw/workspace/output/playwright/hud-broken-live.png', fullPage: false });
  const handles = await page.evaluate(() => {
    const els = [...document.querySelectorAll('*')];
    return els
      .filter(el => {
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return r.width >= 30 && r.height >= 20 && s.cursor === 'pointer' && Number(s.opacity || 1) > 0;
      })
      .map(el => ({
        tag: el.tagName,
        cls: String(el.className || '').slice(0, 120),
        text: (el.textContent || '').trim().slice(0, 60),
        rect: el.getBoundingClientRect().toJSON(),
        bg: getComputedStyle(el).backgroundColor,
        border: getComputedStyle(el).border,
      }))
      .slice(0, 60);
  });
  console.log(JSON.stringify(handles, null, 2));
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });
