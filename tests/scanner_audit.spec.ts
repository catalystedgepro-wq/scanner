import { test, expect } from '@playwright/test';

// Regression guard: every scanner page must render its first data item in <3s.
// Heatmap was stuck at 6-7s because /api/sectors recomputed across 9k tickers per request
// (fix: 5-min in-memory cache in api_server.py:get_sectors, 2026-04-15).
const PAGES: { slug: string; selector: string; min: number }[] = [
  { slug: 'gaps',     selector: '#gap-body tr',                             min: 1  },
  { slug: 'heatmap',  selector: '.sector-tile',                             min: 1  },
  { slug: 'rankings', selector: 'tbody tr',                                 min: 1  },
  { slug: 'sympathy', selector: 'tbody tr, .chain-card, [data-event]',      min: 1  },
];

for (const p of PAGES) {
  test(`${p.slug} renders data within 3s`, async ({ page }) => {
    const t0 = Date.now();
    await page.goto(`https://catalystedgescanner.com/${p.slug}/`, { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForSelector(p.selector, { timeout: 3000 });
    const ms = Date.now() - t0;
    const count = await page.evaluate(s => document.querySelectorAll(s).length, p.selector);
    console.log(`${p.slug} firstRender=${ms}ms items=${count}`);
    expect(count).toBeGreaterThanOrEqual(p.min);
    expect(ms).toBeLessThan(3000);
  });
}

// ── Scanner heatmap descriptor integrity ──────────────────────────────────
// Locks the visible copy to the behavior implemented in generate_seo_site.py::build_heatmap_data.
// If either side drifts, this test fails. Goal: descriptor must always be provably true.
// See memory/scanner_heatmap_descriptor_truth.md for the contract.
test('scanner heatmap descriptor matches build_heatmap_data behavior', async ({ page }) => {
  await page.goto('https://catalystedgescanner.com/scanner/', { waitUntil: 'domcontentloaded', timeout: 10000 });
  await page.waitForSelector('.hm-block', { timeout: 5000 });

  const descriptor = await page.evaluate(() => {
    const p = document.querySelector('.heatmap-sub');
    return p ? p.textContent || '' : '';
  });
  // Required truthful claims (each must survive regeneration):
  expect(descriptor).toContain('Block size');
  expect(descriptor).toContain('total EDGAR filings today');
  expect(descriptor).toContain('Sector → Industry Group → Industry → Sub-Industry');
  expect(descriptor).toContain('Glow color');           // honest: it's box-shadow, not border
  expect(descriptor).toContain('emerald when bullish');
  expect(descriptor).toContain('rose when bearish');
  // Conviction-weighted polarity must be explicitly disclosed — counts alone
  // can mislead (e.g. 1B/1Br with one high-score S-3 reads bearish by weight).
  expect(descriptor).toContain('conviction-weighted');
  expect(descriptor).toContain('gapper_score as weight');
  expect(descriptor).toContain("top-3 conviction sectors");
  expect(descriptor).toContain('Liquid fill level');
  expect(descriptor).toContain('by weight');
  // Must NOT re-introduce overstated / inaccurate claims.
  expect(descriptor).not.toContain('⚡ = score 15+ filing');
  expect(descriptor).not.toMatch(/Border color/i);      // it's a glow, not a border

  // Pulse behavior guard: at most 3 sectors show ⚡ on any given day.
  const pulseCount = await page.evaluate(() => {
    const blocks = Array.from(document.querySelectorAll('.hm-block'));
    return blocks.filter(b => /⚡/.test(b.textContent || '')).length;
  });
  console.log(`heatmap pulse_count=${pulseCount}`);
  expect(pulseCount).toBeLessThanOrEqual(3);

  // Liquid-fill conviction guard: every block has a .hm-fill child whose inline
  // height tracks the WINNING side's share of total conviction weight
  // (bullishWeight + bearishWeight). When no scored filings → 50%. When tied
  // by weight → 50%. When one side dominates → that side's fraction.
  // Verifies the visual matches the data — not a decorative overlay.
  const fillAudit = await page.evaluate(() => {
    const blocks = Array.from(document.querySelectorAll('.hm-block'));
    const data = (window as any)._heatmapData || [];
    const bySector: Record<string, any> = {};
    data.forEach((d: any) => { bySector[String(d.label || d.name || '').toLowerCase()] = d; });
    const out: {label: string; expected: number; actual: number; hasFill: boolean}[] = [];
    for (const b of blocks) {
      const fill = b.querySelector('.hm-fill') as HTMLElement | null;
      const labelEl = b.querySelector('.hm-label');
      const raw = labelEl ? (labelEl.textContent || '') : '';
      const label = raw.replace(/[⚡🏅]/g, '').trim().toLowerCase();
      const d = bySector[label];
      if (!d) continue;
      const bw = d.bullishWeight || 0;
      const xw = d.bearishWeight || 0;
      const total = bw + xw;
      let expected = 50;
      if (total > 0 && bw > xw) expected = (bw / total) * 100;
      else if (total > 0 && xw > bw) expected = (xw / total) * 100;
      const actual = fill ? parseFloat(fill.style.height || '0') : -1;
      out.push({ label, expected, actual, hasFill: !!fill });
    }
    return out;
  });
  expect(fillAudit.length).toBeGreaterThan(0);
  for (const row of fillAudit) {
    expect(row.hasFill, `sector ${row.label} missing .hm-fill`).toBe(true);
    expect(Math.abs(row.actual - row.expected)).toBeLessThan(0.2);
  }

  // Drilldown data-backing guard: first sector block must carry embedded GICS children.
  const drilldownWired = await page.evaluate(() => {
    const anyData = (window as any)._heatmapData;
    if (!Array.isArray(anyData) || anyData.length === 0) return false;
    const first = anyData[0];
    return Array.isArray(first.industryGroups) && first.industryGroups.length > 0;
  });
  expect(drilldownWired).toBe(true);
});
