# UX Coherence Pass · 2026-04-25

Follow-up to `CLICK_PATH_AUDIT.md` #7 and the `/scanner/?q=` regression
(clicking `COIN` from `/defi/` landed on the unfiltered scanner). Three
fixes, idempotent, no page rebuilds.

## Fix 1 — `/scanner/?q=TICKER` now actually filters

`scanner/index.html` got a new `<script>` block (`ceQueryParamFilter`) that:

1. Reads `?q=` (or `?ticker=`) from `URLSearchParams`, sanitises to
   `[A-Z0-9.\-]{≤10}`.
2. Polls briefly for `tr.sr` rows, then hides every row whose `[data-ticker]`
   does not match. Highlights the survivors with a cyan outline. Same logic
   applies to `.sc-filterable` gap-play cards.
3. Inserts a banner above `#results`: `Filtered to TICKER — clear to see all
   catalysts`, with two CTAs — `Open TICKER profile →`
   (`/lookup/?ticker=TICKER`) and `× clear`.
4. Falls back to `No active catalyst rows for TICKER today — try /lookup/`
   when the ticker is not in today's scan.
5. Bonus: delegated click handler so any `strong.clickable-ticker` or
   `.ticker-link[data-ticker]` outside an `<a>` opens `/lookup/?ticker=`.
   Skipped when `defaultPrevented` so existing modal handlers still win.

**Verified via Playwright (live):**

| URL | Banner | Visible | Hidden | Highlighted |
|-----|--------|---------|--------|-------------|
| `/scanner/?q=BCML` | `Filtered to BCML…` | 1 | 27 | 1 |
| `/scanner/?q=COIN` | `No active catalyst rows for COIN today…` | 0 | 28 | — |

Screenshots: `/tmp/visaudit/ux_scanner_filtered.png` (COIN miss case),
`/tmp/visaudit/ux_scanner_bcml.png` (BCML hit case).

## Fix 2 — `← Scanner` breadcrumb on 16 deep pages

Audit listed 18. Two (`/cerebro/`, `/cerebro/app/`) are server-only HUD routes
— their `index.html` does not exist in this docs tree, so they were skipped
(flagging for the server team; the snippet is idempotent and they can paste
it). The remaining **16 pages all got the breadcrumb**, inserted just above
`<section class="cin-hero">`, using the requested polish-token style (IBM
Plex Mono 11px, uppercase, cyan link):

`/dcf/`, `/jackpot/`, `/numerai/`, `/screener/`, `/rankings/`, `/spotlight/`,
`/lookup/`, `/convergence/`, `/darkpool/`, `/options-flow/`, `/congress/`,
`/squeeze/`, `/sectors/`, `/news/`, `/predict/`, `/insiders/`.

Insertion is driven by `/tmp/add_breadcrumb.py` and skips any file already
containing `ce-breadcrumb`, so re-runs are safe.

**Verified Playwright:** breadcrumb on `/dcf/`, `/jackpot/`, `/squeeze/`,
`/insiders/`, `/rankings/`, `/spotlight/` (6/6). Screenshot:
`/tmp/visaudit/ux_dcf_breadcrumb.png`.

## Fix 3 — Ticker-card targets standardised on `/lookup/?ticker=`

`/lookup/index.html` previously auto-loaded a profile only from the URL hash
(`#TICKER`). It now also reads `?ticker=` and `?q=` so every deep-link
convention lands on a working single-ticker view.

**Re-pointed:** `/defi/` Equity Downstream grid (6 cards: COIN, MSTR, RIOT,
MARA, CLSK, HOOD) moved from `/scanner/?q=TICKER` → `/lookup/?ticker=TICKER`.
This is the user's canonical complaint; clicking COIN now opens the full COIN
profile instead of dumping them on the scanner.

**Already correct:** `/jackpot/` pick rows use `/lookup/#TICKER`; the hash
form still works because `/lookup/` reads both.

**No-op:** `/spotlight/` and `/cross-border/` pair-cards have no clickable
ticker target today; out of scope for this pass.

**Other `/scanner/?q=` usages audited:** only `/options-flow/` line 116
(`/scanner/?q=opt`, generic CTA, not a ticker card — left alone). No other
ticker `/scanner/?q=` references in `docs/**/*.html`.

**Verified via Playwright (live):** `/lookup/?ticker=AAPL` now auto-fills the
input and renders the profile (`1 signal detected · RANKED · GAP PLAY · …`).
Screenshot: `/tmp/visaudit/ux_defi_lookup.png` confirms the new `href`.

## Unexpected breaks

None. The delegated `clickable-ticker` handler is gated on `defaultPrevented`
+ "not inside an `<a>`," so per-row handlers (e.g. SEC modals) still take
precedence. To revert, drop the `document.addEventListener('click', …)`
block at the bottom of the new scanner script; everything else is
independent. Two cerebro HUD pages were not in the local tree — server team
can re-run `add_breadcrumb.py`.

## Deploy

`scp` of `scanner/`, `lookup/`, `defi/` + 16 breadcrumb pages to
`cerebro:/opt/catalyst/docs/`. All confirmed via `grep -c 'ce-breadcrumb'`
over SSH and Playwright fetches against the live site.
