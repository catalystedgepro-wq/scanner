import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 45000 });
await page.waitForTimeout(1500);

// Stop the interval
await page.evaluate(() => {
  const max = setTimeout(() => {}, 0);
  for (let i = 0; i <= max; i++) { try { clearInterval(i); clearTimeout(i); } catch (_) {} }
  const cards = document.querySelectorAll('.ts-card');
  cards.forEach((c, i) => c.classList.toggle('ts-active', i === 0));
});
await page.waitForTimeout(700);

// Element-level screenshots
const strip = page.locator('.tactical-strip').first();
const rail = page.locator('.ts-rail').first();
const card = page.locator('.ts-card.ts-active').first();
const headline = page.locator('.ts-card.ts-active .ts-headline').first();

await strip.screenshot({ path: '/tmp/el_strip.png' });
await rail.screenshot({ path: '/tmp/el_rail.png' });
await card.screenshot({ path: '/tmp/el_card.png' });
try {
  await headline.screenshot({ path: '/tmp/el_headline.png' });
} catch (e) {
  console.log('headline shot failed:', e.message);
}

// Also: render headline's bounding box + style to an overlay we screenshot
const info = await page.evaluate(() => {
  const h = document.querySelector('.ts-card.ts-active .ts-headline');
  const l = document.querySelector('.ts-card.ts-active .ts-label');
  const i = document.querySelector('.ts-card.ts-active .ts-icon');
  const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height }; };
  const cs = (el, ...props) => { if (!el) return {}; const s = getComputedStyle(el); return Object.fromEntries(props.map(p => [p, s[p]])); };
  return {
    headline: { rect: r(h), style: cs(h, 'color','fontFamily','fontSize','fontWeight','textShadow','opacity','visibility','display','transform') },
    label:    { rect: r(l), style: cs(l, 'color','fontSize','fontWeight','opacity','visibility','display') },
    icon:     { rect: r(i), style: cs(i, 'color','fontSize','opacity','visibility','display','background') },
  };
});
console.log(JSON.stringify(info, null, 2));

await browser.close();
