# Catalyst Edge — International + DeFi + i18n Master Plan

**Status:** Phase A in progress (2026-04-25). Full plan locked. Work proceeds in
phase order to avoid patch-thrash.

## Architecture (locked)

The scanner is **one unified feed** with multi-select market chips, never a
country toggle. Country pages exist as filtered views for SEO discoverability,
not as parallel scanners. Cross-border convergence is the killer feature
Bloomberg cannot easily replicate.

```
                   ┌─── /scanner/ (unified, default = ALL markets) ─┐
                   │                                                 │
   /international/ │   /international/brazil/   /international/india/│  /defi/
        │          │   /international/japan/    /international/uae/  │    │
        ▼          │              ▼                                   │    ▼
  Country grid     │  Filter view (same data, market chip pre-set)   │  ETF + DeFi
                   │                                                 │
                   └────── one /api/scanner endpoint ────────────────┘
```

## Phase A — Foundation (in progress)

Invisible plumbing every later phase depends on. No UI changes.

| Deliverable | Path | Status |
|---|---|---|
| Unified entity master | `entity_master_intl.csv` | Phase A |
| Add country/currency cols to spokes | `build_intl_equity_gappers.py` | Phase A |
| User-locale + TZ JS helper | `docs/lib/intl.js` | Phase A |
| Currency / number formatter | `docs/lib/intl.js` | Phase A |
| Market filter chip component | `docs/lib/market_filter.js` | Phase A |
| Plan doc (this file) | `docs/PLAN_INTL.md` | ✅ |

## Phase B — Cross-border convergence

Spoke that joins ADR ↔ home-listing pairs and same-sector global cousins.

- `adr_map.csv` — ~150 entity pairs (PETR4↔PBR, BABA↔9988.HK, NVO↔NVS.CO, etc.)
- `build_crossborder_convergence.py` — joins pair signals same day
- `/cross-border/` — top setups page
- JACKPOT scorer: +5 conviction when cross-border convergence overlaps existing JACKPOT

## Phase C — Localization layer (lightweight)

- `<link rel="alternate" hreflang="...">` per country page
- Schema.org `FinancialProduct` + `Country` structured data
- Soft language banner (Accept-Language detected, dismissible, sessionStorage)
- `Intl.NumberFormat` / `Intl.DateTimeFormat` everywhere
- No widget; rely on browser-native translation for the 95% case

## Phase D — Stripe international payments

- Enable `automatic_payment_methods` in Checkout config (SEPA, Pix, UPI, iDEAL auto-shown)
- Turn on Stripe Tax (auto VAT/GST in 50+ jurisdictions)
- Add tax_id collection field for B2B EU
- Single USD price; Stripe handles FX (1% fee)
- Update `/pricing/` copy: "Pay in any currency, local methods supported"

## Phase E — HUD integration

- `MarketFilterRail` chip component using `glassPanel()` from theme.js
- Color nodes by region (Americas / EMEA / APAC / Crypto)
- "Sleep View" toggle: shows what gapped while user's market was closed
- Per CEREBRO_HUD rules: gitnexus_impact on CerebroHUD.jsx, build, deploy, Playwright-verify

## Phase F — Internal docs

- `/docs/international-coverage/` — country grid + currencies + refresh times + sources
- Update `/methodology/` with cross-border scoring math

## Phase G — Translated landing pages (ALL major languages)

**Goal:** capture non-English organic search traffic. Browser translation handles
in-app surfaces; SEO needs pages actually written in the target language.

### Target language tier (by user-base + finance-market activity):

| Tier | Languages | Why |
|---|---|---|
| **T1 (must-have)** | en, es, pt-BR, hi, zh-CN, ar, ja | Largest internet populations + active retail trading |
| **T2 (high-value)** | de, fr, ko, ru, id | Strong financial markets, low translation cost |
| **T3 (extended)** | tr, vi, th, pl, nl, it, sv, he | Emerging fintech adoption |

**Total: ~20 languages.** All pages, one translation pipeline.

### Translation pipeline (no per-page human cost)

1. **Source of truth**: `i18n/strings.json` — all UI/landing copy keyed by string ID
2. **Auto-translate first pass**: DeepL API (free tier 500K chars/month) for the 20 languages
3. **Human review pass**: financial glossary terms locked via DeepL custom dictionary so "short squeeze", "DCF", "convergence" etc. always render correctly
4. **Build step**: `build_localized_pages.py` reads strings.json + templates → generates `/{lang}/scanner/`, `/{lang}/pricing/`, `/{lang}/methodology/`, etc.
5. **hreflang wiring**: every page emits `<link rel="alternate" hreflang="X" href="...">` for all 20 variants + `x-default`
6. **Sitemap**: per-language sitemaps submitted to Google Search Console

### Pages to translate (5 critical pages × 20 langs = 100 pages, all auto-generated):

- `/` (homepage hero)
- `/pricing/`
- `/methodology/`
- `/jackpot/`
- `/dcf/`

Country landing pages get translated INTO their primary language only:
- `/international/brazil/` → Portuguese
- `/international/india/` → Hindi (+ English fallback)
- `/international/japan/` → Japanese
- etc.

### Cost reality

- Pure DeepL auto-translate: **$0** for 100 pages × 1500 chars = 150K chars (well under free tier)
- Glossary review for finance terms: ~3 hours of one-time work to lock 50 key terms in DeepL dictionary
- Human polish for top 3 markets (pt-BR, es, hi): ~$300 one-time on Fiverr if we want it
- Ongoing: zero — re-run pipeline when source strings change

## Order of operations (locked)

```
Phase A (foundation)
   ↓
Phase B (cross-border) ← can ship in parallel with C
Phase C (light i18n)   ← can ship in parallel with B
   ↓
Phase D (Stripe intl)
   ↓
Phase E (HUD)          ← can ship after A is done, doesn't block D
   ↓
Phase F (docs)
   ↓
Phase G (full translation)  ← LAST, depends on Phase C infra
```

## Stripe international notes

- 46 countries supported, 135+ currencies accepted
- Stripe Checkout auto-localizes UI to browser language for free
- `automatic_payment_methods: { enabled: true }` shows SEPA/Pix/UPI/iDEAL/etc.
- Stripe Tax: 0.5% per txn, handles 50+ tax jurisdictions including EU VAT MOSS
- Tax ID collection for B2B EU customers (reverse-charge VAT)
- Single USD base price recommended; Stripe converts at 1% FX fee

## What we are NOT doing

- No on-page translator widget (deprecated pattern; browsers handle it)
- No country-toggle that swaps the entire scanner
- No separate Stripe Price object per country (over-engineered for $9/$39 tiers)
- No JS-runtime i18n framework (bad for SEO; we generate static localized pages)
