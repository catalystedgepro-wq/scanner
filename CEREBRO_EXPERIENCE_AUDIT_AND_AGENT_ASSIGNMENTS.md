# Cerebro Experience Audit And Agent Assignments

## Immediate Answer

Before this pass, there was not a dedicated standing agent whose job was to review both the Scanner and the Cerebro HUD as different user types across the full product journey.

That gap is now explicitly filled.

## Assigned Lanes

### Status Shift After Live Parity Deployment

- `Avicenna`: mission accomplished on the first parity tranche. The live HUD can now rescue Scanner-only picks such as `BRRW` through command search.
- `Hume`: now the active lead for cinematic motion research and the shift from generic glow toward institutional-grade authority.
- `Goodall`: now in recurring cross-surface persona QA across Scanner and HUD after parity closed the most critical discovery gap.
- `Socrates`: now actively tracking trust regressions after parity, including stale/fallback framing, scanner freshness truthfulness, and rescued-node certainty boundaries.
- `Peirce`: now owns the implementation map for the authority tranche, with token consolidation and motion simplification as the immediate design-system priorities.

### Live Authority Tranche Status — 2026-04-08

- Scanner freshness recovery: fixed live cron/install path drift, restored the free newsletter send, and confirmed the public scanner refreshed premarket again.
- Scanner -> HUD handoff: live `Open in Cerebro` CTAs now deep-link into `/#hud?ticker=...&source=scanner` and carry richer handoff context (`rank`, `score`, `form`, `reason`, `channel`).
- HUD handoff consumption: the raw-IP HUD now resolves the handed-off ticker, opens the inspector, preserves parity context, and shows a proper command-rail lock card during acquisition.
- Live regressions caught and fixed: the first handoff deploy exposed a `flashFocusStatus` temporal-dead-zone crash in `CerebroHUD.jsx`, and the first authority deploy still left target lock stuck in `acquiring`; both were patched, rebuilt, redeployed, and re-verified via live browser audits (`NOAH`, then `BAM`).
- Current live status: production Scanner -> HUD handoff now reaches `lock confirmed`.
- Scanner reliability hardening: live Scanner browser quotes are now intentionally degraded to `Snapshot mode` unless explicitly enabled, Finnhub and Polymarket client lanes stay off by default, the public page now registers a versioned service worker (`/sw.js?v=ce-v3`), and a fresh Chromium audit showed no console errors and no remaining AllOrigins/Yahoo proxy failures.
- Current next tranche: branded handoff, calmer field-line behavior, stronger target-lock choreography, and trust-safe degraded-mode messaging.

### `Goodall` — Cross-Surface Experience QA

Owns recurring review of both Scanner and HUD as:

- beginner
- intermediate trader
- expert discretionary trader
- institutional / venture user

Focus:

- discoverability
- search and target lock
- actionability
- workflow continuity from Scanner to HUD
- intimidation vs clarity
- what feels premium vs amateurish

### `Erdos` — UX Persona Audit Lead

Owns persona-specific product critique and psychographic framing.

Focus:

- trust thresholds by persona
- beginner confusion vs expert boredom
- institutional credibility vs retail spectacle
- where visuals help and where they overstate confidence

### `Hume` — Market Research + Motion Intelligence

Owns the “new standard” visual benchmark lane.

Focus:

- cinematic motion systems
- psychographic visual design
- operator-grade atmosphere
- what should feel like Unreal-style broadcast polish without turning into noise

### `Avicenna` — Scanner/HUD Search And Universe Parity

Owns the data and search seam between public Scanner picks and the HUD universe.

Focus:

- why Scanner symbols fail to appear in HUD command search
- entity-master vs scanner-artifact mismatch
- search fallback behavior
- ticker discoverability and target acquisition

### `Socrates` — Evidence And Trust QA

Owns certainty framing across both surfaces.

Focus:

- fact vs inference
- freshness visibility
- provenance
- fallback labeling
- reducing false confidence while preserving premium presentation

### `Peirce` — Design Systems / UI UX Pro Max Implementation

Remains the design owner for implementation once the above audits define the standards.

Focus:

- shared design system
- motion language
- scanner and HUD visual consistency
- turning critique into production UI direction

## Confirmed Product Gap

### Scanner Picks Can Be Missing From HUD Search

This is a real bug, not just a perception issue.

Proof:

- The Scanner spotlight and ranked sections are built from CSV artifacts like:
  - `sec_top_gappers.csv`
  - `sec_catalyst_ranked.csv`
  - `squeeze_candidates.csv`
  - `insider_clusters.csv`
  - `dark_pool.csv`
- The HUD universe and command search are built from `entity_master.json` through `/api/universe`

Relevant files:

- [generate_seo_site.py](/home/operator/.openclaw/workspace/generate_seo_site.py)
- [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)

### Current Code Behavior

- [generate_seo_site.py](/home/operator/.openclaw/workspace/generate_seo_site.py#L856) builds the top pick from Scanner ranking sources
- [generate_seo_site.py](/home/operator/.openclaw/workspace/generate_seo_site.py#L2348) loads the Scanner sections from ranked CSVs
- [api_server.py](/home/operator/.openclaw/workspace/api_server.py#L379) serves `/api/universe` from `entity_master.json`
- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx#L335) loads the HUD universe only from `/api/universe`
- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx#L1168) command search only searches the loaded HUD nodes

### Verified Mismatch Snapshot

Current scanner-source symbols missing from `entity_master.json`:

- `sec_top_gappers.csv`: `13`
- `sec_catalyst_ranked.csv`: `13`
- `dark_pool.csv`: `1`

Examples:

- `BRRW`
- `CDTT`
- `FOAC`
- `GGRO`
- `INVL`
- `KPET-UN`
- `LTRY`
- `MNYW`
- `NMPA`
- `PREN`
- `RNWW`
- `SQLL`
- `VLDX`

That means a top pick can be real on the Scanner and still be impossible to find in Cerebro HUD command search.

## Experience Findings

### What Feels Amateurish Right Now

- Some network-event lines feel like generic alert strokes instead of meaningful cinematic signal
- Visual conviction still sometimes exceeds evidence conviction
- The HUD can look alive, but not always authoritative
- Scanner and HUD still feel related, but not yet like one inevitable operator workflow

### What Needs To Feel Premium

- search and target acquisition
- certainty and provenance cues
- motion that explains state changes
- cleaner Scanner-to-HUD handoff
- cinematic depth without UI clutter

## Motion / Visual Direction

The target is not “more sci-fi.”

The target is:

- cinematic
- high-trust
- stateful
- operator-grade
- psychographically convincing to both beginners and institutions

The standard should feel like:

- an intelligence console for professionals
- a premium scanner for discovery
- one shared visual system with different intensity across both surfaces

## Next Fix Tranches

### Tranche 1 — Data Parity

- Add a Scanner-to-HUD parity layer so every Scanner pick is discoverable in Cerebro
- Either:
  - enrich `entity_master.json` during pipeline runs
  - or add a HUD search fallback that indexes Scanner ranking artifacts

### Tranche 2 — Search UX

- command search suggestions
- preview-before-lock
- explicit “found in Scanner but not mapped in universe” state
- stronger selected-target beacon

### Tranche 3 — Trust Layer

- clearer fact / inference / review-required ladder
- visible provenance and freshness on both surfaces
- calmer presentation for uncertain data

### Tranche 4 — Cinematic Motion System

- severity-led Velocity Deck motion
- sympathy propagation as meaningful chain motion
- macro pressure as field behavior, not noisy decoration
- Scanner card choreography that feels premium rather than gimmicky

### Live Authority Pass Status — 2026-04-08

- `Hume` + `Peirce` authority-motion pass is live on the HUD side:
  - calmer field behavior
  - phase-driven command rail
  - explicit mechanical lock language
  - stronger scanner-handoff state in the operator surface
- Live browser audit confirmed the public HUD now exposes:
  - `scanner handoff`
  - `settling`
  - `lock confirmed`
  - `mechanical state`
  - `cue trigger`
  - `scanner parity`
- Scanner transfer overlay code is implemented in `generate_seo_site.py`, but it is not live on the public Scanner yet.
- The current blocker is the Scanner publish lane itself:
  - stale deployment/scheduler root assumptions were still pointing at `/opt/catalyst`
  - those paths are now patched to the real workspace-root deployment model
  - the remaining failure is upstream EDGAR timeout/rate-limit behavior during `build_only`

## Recommendation

Yes, a permanent market research and insight function should exist on the team.

The product now needs three distinct but connected lanes:

- cross-surface UX QA
- psychographic / market research
- motion-language and premium interaction design

Without them, the team will keep polishing effects without fully solving trust, discoverability, and premium positioning.
