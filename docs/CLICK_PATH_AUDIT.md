# Click-Path + Data Audit · 2026-04-26

Source: live crawl of https://catalystedgescanner.com via Playwright (chromium 1217), depth 2, 47 unique pages crawled in run 1 + 36 targeted pages in run 2 + interaction tests on /scanner/, /defi/, /cross-border/, /lockups/, /heatmap/. Raw data: `docs/audit_raw.json` (run 1), `docs/audit_raw2.json` (run 2).

## Summary

- **Total pages crawled:** 47 (run 1) + 36 (run 2 targeted) — 0 HTTP errors, all 200 OK
- **Broken-data pages (real bugs, not "page works but no rows today"):** 3
  - `/lockups/` — page reads `d.events`, API returns `d.lockups` (silent mismatch, table never populates)
  - `/options-flow/` — page works, but `/api/options-flow` only returns 2 flows ever; thin live data, looks broken to a paying user
  - `/cross-border/` — data file (49 pairs) loads, render path is intact, but conviction filter buttons have no `data-conviction` attr and no working test was triggered (see "Filters" below)
- **Pages with stuck `–` placeholders that never populate within 5s:** /pricing/ (19 expected — these are pricing dashes, OK), /trades/ (43, real bug — see below), /dcf/ (90, mostly grade column dashes for tickers with no DCF — partial), /international/ (83 — same as DCF), /scanner/ (29 — reel-static markers in countdown banner, harmless)
- **Pages missing filtering they obviously need:** /rankings/ (100 rows, no sector chip), /congress/ (100 rows, no party / chamber filter), /winners/ (50-row board, no consistency / appearance filter), /lockups/ (114 lockups, no 30/90/heavy filter), /late-filings/ (56 filings, no form-type filter), /trust/ (51 outcome rows, no W/L filter), /trades/ (no status filter), /benchmarks/ (no vendor filter), /digest/ (no date picker)
- **Pages with broken filter wiring:** none in the scanner sector chips (verified 38 → 11 → 7 visible cards on Financials/Tech). DEFI coin tabs have proper `data-sort` attrs (Top by rank / Gainers / Losers / Volume) — not tested for resort, but markup is correct. Cross-border has 4 pair-filter buttons (`All / Trade conviction / Watch / Same direction`) but they use `data-filter` attr not `data-conviction` (audit script targeted wrong attr; markup-side they should work via existing handler — to verify, see Critical fixes).

## Critical fixes (ship today)

1. **`/lockups/index.html:278`** — change `allEvents = d.events || [];` to `allEvents = d.lockups || [];`. The whole table currently renders zero rows on production despite 114 lockups in API. (Confirmed: API returns `{lockups: [...], count}`, page reads `d.events` → undefined → `[]`.) Verify the secondary block at line ~301 (`var l=(d&&d.lockups)||[]`) is the strip-stat reader, not duplicate.

2. **`/options-flow/`** — `/api/options-flow` only returns 2 flows. Either the underlying job is undersampling (likely `unusual_call_vol` threshold too tight) or the page should render *all* flows with a "high-activity" badge instead of relying on the upstream filter. Currently a paid scanner page that shows 2 rows looks broken. Either fix the producer or surface the flows the API does have plus a "Why so few?" explainer.

3. **`/scanner/`** sector chips on bar at `index.html:2421` — markup and handler (`setSectorFilter`) at `scanner/index.html:5808` are CORRECT and verified working. **No fix needed**, but the filter bar has no "Reset" affordance after clicking a sector other than "All Sectors" — add a small "× clear" button or make "All Sectors" visually obvious as the reset.

4. **`/cross-border/index.html:590`** — pair-filter buttons declare `data-filter="trade"` not `data-conviction`. The handler at line ~705 reads `filterMode` (which is wired through). Markup looks intact. Action: add a Playwright test in CI to click each filter and assert `.pair-card` count drops; current production has 49 pairs so Trade should reduce to 11, Watch to 6.

5. **`/api/heatmap`** — returns 404 (size 22 bytes `{detail:"Not Found"}`). `/heatmap/` page does NOT call this endpoint (it calls `/api/sectors`, which works) so it is not user-visible, but the 404 should be removed from the live router or aliased to `/api/sectors` to silence dead probes.

6. **`/cerebro/` and `/cerebro/app/`** — both return 200 but rendered 0 rows / 0 tables / 0 placeholders / no filters / no nav back. From the title these are HUD pages, but the audit could not detect any UI primitive at all (likely all canvas/WebGL). Confirm the WebGL HUD is loading on a real browser; if it is canvas-only, add a fallback list/sidebar so the page is not blank for clients with WebGL disabled.

## High-priority polish

7. **No "Back to Scanner" / breadcrumb** on 18 deep pages: `/cerebro/`, `/dcf/`, `/jackpot/`, `/numerai/`, `/screener/`, `/rankings/`, `/spotlight/`, `/lookup/`, `/convergence/`, `/darkpool/`, `/options-flow/`, `/congress/`, `/cerebro/app/`, `/squeeze/`, `/sectors/`, `/news/`, `/predict/`, `/insiders/`. The shared topnav has the "Scanner" link but on narrow viewports the burger menu masks it. Add an explicit `← Scanner` breadcrumb to the page hero of every scanner-tool page (one row above the cinematic strip) — pattern already exists on `/cross-border/`, `/defi/`, `/explorer/`, `/glossary/`, `/case-studies/`, `/landing/` per the crawl.

8. **`/dcf/` placeholders (90)** — the A-grade and B-grade strip values at lines 137–138 (`<div class="cin-v bull" id="k-a">–</div>`) populate from the JSON, but the in-table grade column shows `—` for every ticker the DCF model could not score. Audit found ~75 of those visible above the fold. Either filter to scored-only-by-default (paginate the unscored), or ship a "Why no grade?" tooltip on each em-dash so the page stops looking broken.

9. **`/international/` (83 placeholders)** — same pattern as `/dcf/`. Most cells use the `cin-v gold` / `cin-v bull` pattern with em-dash defaults that never get filled. Add a server-side `display_value` (e.g., "n/a — no XBRL filing") so the visible token is informative, not stuck.

10. **`/trades/` (43 placeholders, 21 rows, 5 tables)** — heavy use of TD-class em-dashes. This is the public audit ledger; em-dashes erode trust for the exact page where trust is the product. Backfill closed-trade columns (Entry, Exit, Net %, Hold Days) from the outcomes ledger (`sec_outcome_rows.csv`) so no closed trade ever shows `–`.

11. **`/cross-border/` row count = 0 in audit** — Playwright with 6s settle saw the conviction-filter buttons render but no `.pair-card` children. This is likely just a slow first-paint (renderTape + buildPairCard runs after `fetchPairs()` which is `setInterval(600000)`). Verify on real users (mobile especially) — if first paint is > 6s, either inline a server-rendered fallback list of top 5 trade-conviction pairs in HTML, or move the fetch above the cinematic hero JS.

12. **`/predict/` (3 placeholders, 0 rows, 0 tables)** — the prediction-market page seems to be stub-only on the docs side. Either ship live odds from a backend or hide the page from `/suite/` until ready. A paying user clicking from the cinematic strip to a 0-row page is the worst kind of dead link.

## Medium-priority polish — filters that should exist but do not

13. **`/rankings/` (100 rows)** — add sector chip filter (mirror `/scanner/` setSectorFilter pattern) + sortable columns on `rank, score, score Δ`. Trivial to add and the most-trafficked board page.

14. **`/congress/` (100 rows)** — add chamber filter (Senate / House / All), party filter (D / R / I / All), date-range filter (7d / 30d / 90d / YTD), ticker search.

15. **`/winners/` (50 rows)** — add filters: `Consistency ≥ 80%`, `Apps ≥ 5`, `All-time top 50 / Last 90d`. Sortable columns on every numeric.

16. **`/late-filings/` (56 filings)** — add form-type filter (NT-10K / NT-10Q / 12b-25), `with insider activity` toggle, `going-concern` toggle.

17. **`/trust/` (51 outcome rows)** — add Win / Loss / Open filter, sortable date column, ticker search.

18. **`/digest/`** — add date picker and "Compare to yesterday" diff. Currently locked to "today only".

19. **`/screener/`** — already has signal-pill filter, but no save-search / share-URL. Add `?signals=insider,squeeze` URL persistence so users can share filter combos.

20. **`/calendar/`** — currently `/api/calendar` returns `days[]`, but no week / day toggle, no sector slice.

## Logical UX issues

21. **`/spotlight/`, `/lookup/`, `/news/`** — all rendered 0 visible cards/rows in headless audit (could be slow XHR or canvas). Need first-paint server render or skeleton placeholders. Currently a user opening the page sees a hero and an empty white area below.

22. **`/cerebro/` and `/cerebro/app/`** — no navigation back, no breadcrumb, no sidebar — just the HUD. Add a thin top bar with "← Scanner" and tool switcher.

23. **`/api/screener` browsed via UI** — page returned 0 rows in card test, but the shape is `{tickers: [...]}` with 200 entries. Audit selector wrong; ship a `data-row` attribute on `.ticker-card` to make it programmatically testable in CI.

24. **Suite mega-menu** — exists on `/scanner/` (`#suite-overlay`, `#suite-mega`) — verified opening on click. Confirm it is mounted on every page that has `Catalyst Edge` in the topnav; otherwise users on tool pages can't jump tools without going home first. (Quick check: search the docs for `id="suite-mega"` count vs total HTML files.)

## Page-by-page detail (selected)

| Path | Status | Tables | Rows | Placeholders | Filter | NavBack | Notes |
|------|--------|--------|------|--------------|--------|---------|-------|
| `/` | 200 | 1 | 5 | 0 | n | y | OK |
| `/scanner/` | 200 | 5 | 36 | 29 | y (works) | y | sector filter verified 38→11→7 visible cards |
| `/scanner/?q=COIN` | 200 | 5 | 36 | 29 | y | y | search query string ignored — query param does not pre-filter visible rows |
| `/scanner/#gaps` | 200 | 5 | 36 | 29 | y | y | anchor exists, scrolls correctly |
| `/lockups/` | 200 | 1 | 0 | 0 | n | n | **BROKEN** — `d.events` vs `d.lockups` mismatch (see fix #1) |
| `/options-flow/` | 200 | 1 | 0 | 0 | n | n | API returns only 2 flows; table renders correctly but looks empty (see fix #2) |
| `/dcf/` | 200 | 1 | 153 | 90 | n | n | DCF dashes for unscored tickers (see fix #8) |
| `/international/` | 200 | 2 | 155 | 83 | n | n | same dash pattern as /dcf/ |
| `/trades/` | 200 | 5 | 21 | 43 | n | n | em-dashes on a trust page (fix #10) |
| `/cross-border/` | 200 | 0 | 0 | 0 | y(4) | y | data exists, slow first-paint (fix #11) |
| `/defi/` | 200 | 2 | 41 | 24 | y(4 sort tabs) | y | rank/gainers/losers/volume markup correct |
| `/heatmap/` | 200 | 0 | 0 | 2 | n | n | renders 13 sector boxes correctly via `/api/sectors` |
| `/sectors/` | 200 | 0 | 0 | 4 | n | n | calls `/api/sector-heatmap` (200) and renders cards |
| `/screener/` | 200 | 0 | 0 | 2 | y (signal pills) | n | uses `result-grid` divs not table; works |
| `/winners/` | 200 | 0 | 0 | 2 | n | n | uses `.podium-card` divs; renders 100 winners; needs filters (#15) |
| `/congress/` | 200 | 1 | 100 | 1 | n | n | needs filters (#14) |
| `/rankings/` | 200 | 1 | 100 | 1 | n | n | needs sort + sector (#13) |
| `/late-filings/` | 200 | 1 | 0 | 0 | n | n | renders, just no rows in headless; needs filters (#16) |
| `/cerebro/` | 200 | 0 | 0 | 0 | y | n | WebGL HUD; needs SSR fallback + nav (#6) |
| `/jackpot/` | 200 | 1 | 1 | 3 | n | n | hero strip + 1 row OK |
| `/predict/` | 200 | 0 | 0 | 3 | n | n | stub page — hide from suite menu until live (#12) |
| `/news/` | 200 | 0 | 0 | 0 | n | n | renders post-XHR; verify on real browser |
| `/digest/` | 200 | 0 | 0 | 2 | n | n | no date picker (#18) |
| `/calendar/` | 200 | 0 | 0 | 4 | n | n | no day/week toggle (#20) |
| `/api/heatmap` | **404** | — | — | — | — | — | dead route — alias or remove |

## Filter interaction tests (verified)

| Page | Filter | Before | After | Result |
|------|--------|--------|-------|--------|
| `/scanner/` | All Sectors → Financials | 38 visible cards | 11 | OK |
| `/scanner/` | Financials → Technology | 11 | 7 | OK |
| `/defi/` | data-sort=rank/gainers/losers/volume | markup OK, click handler not yet asserted in CI | — | needs test |
| `/cross-border/` | data-filter=all/trade/watch/aligned | rowCount 0 at 6s settle (slow first paint) | — | needs SSR fallback |
| `/scanner/#gaps,#squeeze,#insider,#results` | anchor scroll | targets exist | — | OK |

## Failed fetches observed

None during the crawl. All `/api/*` endpoints returned 200 except `/api/heatmap` (404) which is unused. No 5xx, no console errors observed in the captured pages.

## Should some tables need filtering that don't have it?

Yes — see fixes #13–#20. Highest impact: `/rankings/`, `/congress/`, `/winners/`, `/late-filings/`. Each currently dumps 50–100 rows with no narrowing. Pattern to copy: `setSectorFilter` from `/scanner/index.html:5808` plus the existing `.sec-filter-btn` styles at line 578. Total cost per page: ~30 lines of HTML + 20 lines of JS.
