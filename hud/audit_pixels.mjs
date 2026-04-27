import { chromium } from 'playwright';
import fs from 'fs';

const CHROME = '/home/operator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'networkidle', timeout: 45000 });
await page.waitForTimeout(2000);

// Force scroll to top and ensure nothing shifted
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(200);

// Take a full viewport screenshot
await page.screenshot({ path: '/tmp/full_top.png', clip: { x: 0, y: 0, width: 1440, height: 300 } });

// Use canvas sampling from the page itself — render to data URL then sample
const info = await page.evaluate(() => {
  const headline = document.querySelector('.ts-card.ts-active .ts-headline');
  if (!headline) return { error: 'no headline' };
  const r = headline.getBoundingClientRect();
  const strip = document.querySelector('.tactical-strip');
  const stripR = strip.getBoundingClientRect();
  const card = document.querySelector('.ts-card.ts-active');
  const cardR = card.getBoundingClientRect();

  // Get any parent opacity/clip chain
  const chain = [];
  let el = headline;
  while (el && el !== document.body) {
    const s = getComputedStyle(el);
    chain.push({
      tag: el.tagName + (el.className ? '.' + String(el.className).replace(/\s+/g, '.') : ''),
      opacity: s.opacity,
      filter: s.filter,
      clipPath: s.clipPath,
      transform: s.transform,
      overflow: s.overflow,
      backdropFilter: s.backdropFilter,
      mixBlendMode: s.mixBlendMode,
      color: s.color,
      background: s.backgroundColor,
    });
    el = el.parentElement;
  }
  return {
    headline_rect: { top: r.top, left: r.left, w: r.width, h: r.height },
    strip_rect: { top: stripR.top, left: stripR.left, w: stripR.width, h: stripR.height },
    card_rect: { top: cardR.top, left: cardR.left, w: cardR.width, h: cardR.height },
    chain,
  };
});

console.log(JSON.stringify(info, null, 2));
await browser.close();
