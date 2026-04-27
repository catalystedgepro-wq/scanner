import { chromium } from 'playwright';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'networkidle', timeout: 45000 });
await page.waitForTimeout(1200);

const report = await page.evaluate(() => {
  const rail = document.getElementById('ts-rail');
  const cards = [...document.querySelectorAll('.ts-card')];
  const wrap = document.querySelector('.ts-wrap');
  const dots = document.querySelector('.ts-dots');
  const cta = document.querySelector('.ts-cta');

  const dump = (el, label) => {
    if (!el) return { label, missing: true };
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return {
      label,
      rect: { top: r.top, left: r.left, w: r.width, h: r.height },
      display: s.display, visibility: s.visibility, opacity: s.opacity,
      pos: s.position, zIndex: s.zIndex,
      flex: s.flex, flexBasis: s.flexBasis,
      minHeight: s.minHeight, height: s.height,
      overflow: s.overflow,
      text: el.innerText ? el.innerText.slice(0, 90) : '',
      childCount: el.children.length,
    };
  };

  return {
    wrap: dump(wrap, 'ts-wrap'),
    rail: dump(rail, 'ts-rail'),
    dots: dump(dots, 'ts-dots'),
    cta: dump(cta, 'ts-cta'),
    cards: cards.map((c, i) => {
      const isActive = c.classList.contains('ts-active');
      const d = dump(c, `card[${i}]${isActive ? ' ACTIVE' : ''}`);
      d.tint = c.style.getPropertyValue('--ts-tint') || '';
      const label = c.querySelector('.ts-label');
      const head = c.querySelector('.ts-headline');
      const detail = c.querySelector('.ts-detail');
      d.labelText = label?.innerText || '';
      d.headText = head?.innerText || '';
      d.detailText = detail?.innerText || '';
      if (head) {
        const hr = head.getBoundingClientRect();
        const hs = window.getComputedStyle(head);
        d.headRect = { w: hr.width, h: hr.height, top: hr.top, left: hr.left };
        d.headColor = hs.color;
        d.headVisible = hs.visibility;
        d.headOpacity = hs.opacity;
      }
      return d;
    }),
  };
});

console.log(JSON.stringify(report, null, 2));
await browser.close();
