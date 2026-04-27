import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const URL = 'https://catalystedgescanner.com/scanner/';

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const consoleMsgs = [];
page.on('console', m => consoleMsgs.push(`${m.type()}: ${m.text()}`));
page.on('pageerror', e => consoleMsgs.push(`PAGE_ERROR: ${e.message}`));

await page.goto(URL, { waitUntil: 'networkidle', timeout: 45000 });
await page.waitForTimeout(1500);

const report = await page.evaluate(() => {
  const strip = document.querySelector('.tactical-strip');
  const wrap = document.querySelector('.tactical-strip .ts-wrap');
  const cards = document.querySelectorAll('.tactical-strip .ts-card');
  const active = document.querySelector('.tactical-strip .ts-card.active');
  const nav = document.querySelector('nav, .site-nav, header');

  const rect = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return {
      top: r.top, left: r.left, w: r.width, h: r.height,
      display: s.display, visibility: s.visibility, opacity: s.opacity,
      background: s.backgroundImage || s.backgroundColor,
      zIndex: s.zIndex, position: s.position, overflow: s.overflow,
      color: s.color,
    };
  };

  // Find what's at the strip's center point
  let stackedEls = [];
  if (strip) {
    const r = strip.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    stackedEls = document.elementsFromPoint(cx, cy).slice(0, 8).map(el => ({
      tag: el.tagName, cls: el.className?.slice?.(0, 80) || '', id: el.id || ''
    }));
  }

  return {
    found_strip: !!strip,
    strip: rect(strip),
    wrap: rect(wrap),
    card_count: cards.length,
    active_card: rect(active),
    active_card_text: active?.innerText?.slice(0, 200) || '',
    nav: rect(nav),
    stacked_at_center: stackedEls,
    body_bg: window.getComputedStyle(document.body).backgroundColor,
    viewport: { w: window.innerWidth, h: window.innerHeight, scrollY: window.scrollY },
  };
});

await page.screenshot({ path: '/tmp/strip_viewport.png', fullPage: false });

if (report.strip) {
  const s = report.strip;
  await page.screenshot({
    path: '/tmp/strip_region.png',
    clip: {
      x: Math.max(0, s.left - 10),
      y: Math.max(0, s.top - 10),
      width: Math.min(1440, s.w + 20),
      height: Math.min(900 - Math.max(0, s.top - 10), s.h + 20),
    },
  });
}

console.log(JSON.stringify({ report, consoleMsgs: consoleMsgs.slice(0, 20) }, null, 2));

await browser.close();
