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

const info = await page.evaluate(() => {
  const h = document.querySelector('.ts-card.ts-active .ts-headline');
  const l = document.querySelector('.ts-card.ts-active .ts-label');
  const body = document.querySelector('.ts-card.ts-active .ts-body');
  const card = document.querySelector('.ts-card.ts-active');
  const icon = document.querySelector('.ts-card.ts-active .ts-icon');
  const get = (el, ...p) => { if (!el) return {}; const s = getComputedStyle(el); const r = el.getBoundingClientRect(); const o = {rect: {w: r.width, h: r.height, x: r.left, y: r.top}}; p.forEach(k => o[k] = s[k]); return o; };

  // Check what font-family actually resolves and if it has glyphs
  const testProps = ['lineHeight','fontSize','fontFamily','fontVariant','textRendering','writingMode','fontStretch','fontSynthesis','fontOpticalSizing','textOrientation','letterSpacing','wordSpacing','whiteSpace','direction','color','webkitTextFillColor','webkitTextStroke'];
  return {
    card: get(card, ...testProps),
    body: get(body, ...testProps, 'flexBasis','flexGrow','flexShrink','alignItems','justifyContent','flexDirection'),
    icon: get(icon, ...testProps, 'width','height'),
    label: get(l, ...testProps),
    headline: get(h, ...testProps),
  };
});

console.log(JSON.stringify(info, null, 2));
await browser.close();
