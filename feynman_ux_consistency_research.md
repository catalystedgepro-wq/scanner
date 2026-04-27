# Feynman research brief — Catalyst Edge UX/UI consistency audit

**Owner:** Catalyst Edge Scanner founder
**Operator:** Feynman (research agent)
**Date issued:** 2026-04-25
**Output:** `/home/operator/.openclaw/workspace/feynman_ux_audit_report.md`
**Estimated effort:** ~3-4 hours of focused research; deliverable is a written report, not a code patch.

---

## 1. Context — what Catalyst Edge is

Catalyst Edge Scanner is a public Bloomberg-alternative trading-research site (`https://catalystedgescanner.com`) plus an internal Cerebro HUD (`/cerebro/app/`). The product is built on a deliberate visual language:

- **Palette:** navy `#04070d`, cyan `#5ad7ff`, gold `#f5c662`, bull `#5cf2a4`, bear `#ff6b8b`, ink `#e6f1ff`, ink-dim `#9bb0c8`, ink-mute `#6e8198`.
- **Typography:** body in system sans; accents/eyebrows/badges in `IBM Plex Mono` (uppercase, 0.18em letter-spacing).
- **Surface treatment:** glass panels `linear-gradient(180deg, rgba(15,28,48,0.78), rgba(7,14,28,0.78))` with `1px solid rgba(110,140,180,0.18)` borders, 14-18px radii, navy/cyan/gold tactical aesthetic.
- **Component idioms:** `.intel-shell`, `.suite-card`, `.tier`, `.guard`, `.live-pill`, `.api-status`, `.audit-summary` pills, `.ang` (narrative angle cards), `.case-study` cards.

The **canonical reference page** is `https://catalystedgescanner.com/scanner/`. Every other page in the ecosystem should match its visual language. Many do; some don't.

---

## 2. The specific problem this brief is about

**When a user clicks any outbound link (SEC EDGAR, a news article, the Cerebro HUD, Stripe, etc.), they should always see a consistent contextual summary BEFORE they click out.** Today this works on `/scanner/` but is missing or inconsistent on other pages — including the Cerebro HUD.

### The canonical pattern from `/scanner/`

When a user hovers/focuses a `View SEC Filing ↗` link, a tooltip surfaces this 3-line summary:

```
HBIA
8-K
Material corporate event — company required to disclose significant news ·
High-conviction setup — gap score 23 ·
No additional risk keywords were detected in the filing scan
View Full Filing on EDGAR ↗
```

Implementation location: `data-summary` attribute on `.btn.btn-outline.sc-sec-link` elements in `/opt/catalyst/docs/scanner/index.html`, rendered via the existing tooltip CSS.

### Where this pattern is missing or inconsistent

The user has called out (and Feynman should verify):

1. **Cerebro HUD outbound links** (`/cerebro/app/`) — clicking through to SEC, news, or Numerai often skips the summary entirely.
2. **`/international/` panels** — country-tape headlines link directly to source URLs with no pre-click context.
3. **`/dcf/`, `/trust/`, `/benchmarks/`** — outbound `docs.alpaca.markets`, `damodaran.nyu.edu`, `numerai.com` links sometimes bare.
4. **Blog posts under `/blog/*`** — external (Stripe, EDGAR) often missing the summary scaffold.
5. **`/explorer/`** (API playground) — endpoint buttons don't surface what they return until clicked.

The user wants **one consistent pattern across the entire ecosystem**. Feynman's job is to (a) inventory the inconsistencies, (b) propose a unified pattern, and (c) cost-estimate the implementation.

---

## 3. Scope — every page Feynman must inspect

Pull the live sitemap to enumerate the surface:

```bash
curl -s https://catalystedgescanner.com/sitemap.xml | grep -oE '<loc>[^<]+</loc>'
```

The sitemap currently lists 49 public URLs. In addition, inspect:

- Cerebro HUD shell at `https://catalystedgescanner.com/cerebro/app/` (React build, served from `/opt/catalyst/docs/hud/`)
- Embed widgets at `/embed/dcf-top/` and the gallery at `/embed/`
- The four data-driven JSON dashboards (`/trades/`, `/status/`, `/data/api/`, `/explorer/`)
- All pages under `/blog/*/`

For each page, record:

| Field | Notes |
|---|---|
| URL | full path |
| Page category | landing / scanner / valuation / audit / blog / legal / dev / hud |
| Outbound-link count | every `<a>` with `target="_blank"` or non-`catalystedgescanner.com` href |
| Summary tooltip present? | yes/no/partial |
| Brand surface match? | colors, typography, IBM Plex Mono accents, glass panels |
| Component reuse score | 0-3 (0 = uses none of the canonical idioms; 3 = fully consistent) |
| Notable deviations | inline notes |

---

## 4. Deliverables — write this report

Save to `/home/operator/.openclaw/workspace/feynman_ux_audit_report.md`.

### Section A: Inventory table
Per-URL audit with the 6 columns above. Sort by component-reuse score ascending so the worst offenders surface first.

### Section B: Inconsistency catalog
Group findings into themes. Expected categories:
- **Outbound-link summary tooltips** — the headline issue. Where missing, where degraded, where inconsistent in copy/format.
- **Top nav drift** — does each page use the same `topbar-row` + `nav.nav` + suite-cards row, or do older pages have a stripped-down nav?
- **Color drift** — pages using off-brand colors (e.g. pure black, neutral grays not from the palette).
- **Typography drift** — IBM Plex Mono missing on accents; system sans body inconsistent.
- **Tabulation/table styling** — `.intel-table` is canonical; identify any tables not using it.
- **Empty-state design** — `.intel-empty-state` pattern used on `/scanner/`; check whether other pages with empty data fall back to plain text or borrowed bootstrap-style messages.

### Section C: Recommended unified pattern

Propose a single reusable component, e.g.:

```html
<a class="ext-link" href="..." target="_blank" rel="nofollow"
   data-summary-ticker="HBIA"
   data-summary-form="8-K"
   data-summary-detail="Material corporate event — company required to disclose significant news · High-conviction setup — gap score 23 · No additional risk keywords were detected in the filing scan"
   data-cta-label="View Full Filing on EDGAR">
   View Full Filing on EDGAR ↗
</a>
```

with one shared CSS+JS module (e.g. `/lib/ext-summary.js`) that renders the tooltip identically everywhere — scanner, HUD, blog, embed widgets, every internal panel that links out. The Cerebro HUD is React; recommend either a port of the same module or a thin wrapper that emits the same `data-summary-*` attributes onto its anchor elements.

### Section D: Implementation cost estimate

Per page, estimate the effort to retrofit:
- Trivial (≤15 min): pages already on the canonical brand stack, just need the summary attributes.
- Small (~1 hour): pages using the brand stack but missing the tooltip module.
- Medium (~3 hours): pages with brand drift that need surface refactor + tooltip retrofit.
- Large (~1 day): the Cerebro HUD (React, separate build, requires gitnexus_impact on `CerebroHUD.jsx`).

Total estimate at the bottom of the report.

### Section E: Three highest-impact fixes
Pick the three changes that would move the ecosystem closest to "feels like one product" with the least engineering cost. For each: short justification, the affected files, the exact change.

### Section F: Long-tail nice-to-haves
Anything else you noticed during the audit but isn't worth blocking the main fix on. (e.g. favicon variants, OG image regen, dark/light mode toggles.)

---

## 5. Constraints + non-goals

- **Don't write any code.** This is a research deliverable, not a patch. Concrete recommendations only.
- **Don't propose a redesign.** The canonical `/scanner/` aesthetic is not up for debate — every other page should match it, not the other way around.
- **Don't touch `CerebroHUD.jsx` directly.** Per CARL_HUD rule 2, that file is 4,900+ lines with blast radius. Any HUD recommendation must be advisory + reference `gitnexus_impact` for the actual edit.
- **Respect the data-tier paywall.** Some panels are intentionally Pro-tier-locked; don't flag them as "broken UX" if the lock is the design.
- **No CARL/MCP integration suggestions.** Out of scope.

---

## 6. How to run

```bash
# Sample reconnaissance commands Feynman should use:
curl -s https://catalystedgescanner.com/scanner/ | grep -E 'data-summary|data-tip' | head -20
curl -s https://catalystedgescanner.com/sitemap.xml | grep -oE '<loc>[^<]+</loc>' | sed 's/<loc>//;s|</loc>||'
diff <(curl -s https://catalystedgescanner.com/scanner/ | grep -c 'class="intel-shell') \
     <(curl -s https://catalystedgescanner.com/international/ | grep -c 'class="intel-shell')
```

Use Playwright (per CARL_HUD rule 3) for any HUD verification — DOM-only inspection is unreliable on the WebGL force-graph shell.

When done, drop the report at the output path and ping the founder for review. No deploys, no commits.

---

**End of brief.**
