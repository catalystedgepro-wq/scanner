# Sprint Fixes · 2026-04-26

12 audit fixes shipped. Deploy: `scp <file> cerebro:/opt/catalyst/docs/<path>`.
Screenshots: `docs/screenshots/sprint_2026-04-26/`. Verifier: `/tmp/verify_sprint.js`
(Playwright chromium-1217, 1440×900, headless — all 11 runs `ok: true`).

## Track 1 — Critical

### A. /options-flow/ — explainer banner
- File: `docs/options-flow/index.html` · CSS lines 47–54, banner markup ~110–119, JS gate 148–154.
- Change: "Why so few?" banner reveals when `flows.length ≤ 5`. Links to `/scanner/?q=opt`, `/squeeze/`, `/convergence/`. Live API ships only 2 flows (yfinance fallback; options keys not configured).
- Verify: 2 rows + banner visible. Screenshot `options-flow.png`.

### B. /scanner/ — `× Clear filter` chip
- File: `docs/scanner/index.html` · CSS ~582, markup line 2421, JS 5808+.
- Change: Cyan-tinted clear chip appears beside "All Sectors" only when a sector other than All is active. Click resets. Hover lifts with `--shadow-soft`.
- Verify: hidden by default → visible after clicking Financials. Screenshots `scanner-default.png`, `scanner-after-financials.png`.

### C. /cross-border/ — SSR fallback
- File: `docs/cross-border/index.html` lines 595–725 (5 static `.pair-card` blocks); line 583 hero count `5`.
- Change: Top 5 TRADE pairs (SAP, SFTBY, NTDOY, LPL, GMBXF) baked as static HTML. Live `fetchPairs` replaces them once JSON arrives. Eliminates 6s+ first-paint blank state.
- Verify: raw HTML returns 5 `data-ssr="1"` cards; post-JS 25 live cards. Screenshot `cross-border.png`.

### D. /api/heatmap — DEFERRED
- Touching `api_server.py` flagged HIGH risk (7,325 GitNexus deps). Page calls `/api/sectors` (works) so 404 is not user-visible. Follow-up: alias `/api/heatmap → /api/sectors` after `gitnexus_impact`.

### E. /cerebro/ — N/A
- Page does not exist in `docs/`. Only `/cerebro-landing/` is in deploy scope.

## Track 2 — Filters

### 13. /rankings/ — chips + sortable cols
- File: `docs/rankings/index.html` · CSS 47–62, markup 110–118, JS 137–270.
- Live `/api/rankings` ships empty `sector_tags` for all 100 picks → fallback to **score-tier chips**: High≥30, Mid 15–30, SEC, Gappers, Value, News heat (italic hint explains). Sortable headers `#`, `Total`, `Score Breakdown`.
- Verify: 6 chips, 100 rows, click chip 3 → 16 rows. Screenshot `rankings.png`.

### 14. /congress/ — party + date-range
- File: `docs/congress/index.html` lines 143–166 (filter rows), 218+ (state), 311+ (filter logic), 354+ (handlers).
- Adds Party (D/R/I/All) and Window (7d/30d/90d/YTD/All) — chamber and buy/sell already existed. Default window 90d. Composes with existing ticker search.
- Verify: 4 party + 5 date buttons. Screenshot `congress.png`.

### 15. /winners/ — quality filters
- File: `docs/winners/index.html` lines 56–62, 132–140, 162–172, 274, 315+.
- 4 chips: All-time top 50 / Last 90d / Consistency ≥ 80% / Apps ≥ 5. Sort row preserved.
- Verify: 4 filter buttons. Screenshot `winners.png`.

### 16. /late-filings/ — form + toggles
- File: `docs/late-filings/index.html` lines 53–58, 102–110, 137–192.
- 4 form chips (All / NT 10-K / NT 10-Q / 12b-25), 2 toggles (insider buy, going-concern). Refactored render into `renderRows()` + `passes()`.
- Verify: 4 form + 2 toggle buttons. Screenshot `late-filings.png`.

### 17. /trust/ — W/L/Open + search + date sort
- File: `docs/trust/index.html` lines 290–304 (controls), 528+ (script).
- Wins/Losses/Open chips, ticker search input, date sort toggle. Hides static rows in place.
- Verify: 4 buttons + search + sort all present. Screenshot `trust.png`.

### 18. /screener/ — URL persistence
- File: `docs/screener/index.html` lines 187–207 (read/writeURLState), 217+ (button restore), 240+ (handlers).
- Reads `?signals=insider,squeeze&min=3&q=AAPL` on load; writes back via `history.replaceState`. Bookmarkable filter combos.
- Verify: visiting `?signals=insider,squeeze&min=3` activates 2 pills + select reads "3". Screenshot `screener-with-url.png`.

### 19. /calendar/ — week/day toggle
- File: `docs/calendar/index.html` lines 53–67 (CSS), 109–113 (toggle), 137–283 (split into `renderDays`, `renderWeek`, `renderView`).
- ISO-week buckets show total picks, day count, avg score, avg top per week. Default Day.
- Verify: 2 toggle buttons. Screenshot `calendar.png`.

## Files modified

`options-flow`, `scanner`, `cross-border`, `rankings`, `congress`, `winners`,
`late-filings`, `trust`, `screener`, `calendar` — all `index.html`.
Each deployed live to `cerebro:/opt/catalyst/docs/`.
