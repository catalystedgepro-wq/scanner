# Catalyst Edge — Cyberpunk Upgrade Audit

Note on sources: every `design-md/<brand>/README.md` in this collection is a stub pointing at `getdesign.md`. References below are derived from each brand's documented public visual system, mapped against the existing `cyber-shell.css` / `cinematic-hero.css` so the upgrades drop in cleanly.

---

## Top 5 Design References

### 1. SpaceX — `getdesign.md/spacex`
**Why**: Closest analog to a trading scanner that wants "mission control." Editorial typography over telemetry, deep space negatives, monospace data, ultra-wide hero plates.
**Extract**:
- D-DIN / wide condensed display face for hero numerics (Orbitron is fine, but kill the rounded weights — go 800–900 only).
- Massive full-bleed hero "plate" with a single colossal stat and a thin monospace caption below it.
- Lower-third **mission readout strip** (mono labels, right-aligned values, pipe separators).
- Black-as-canvas with one accent (their hero accents are paper-white; ours stays cyan).
- T-minus countdown pattern → reuse for "next earnings / next FOMC."

### 2. NVIDIA — `getdesign.md/nvidia`
**Why**: Production cyberpunk done with restraint. Green is their signature, but the mechanics (gradient mesh hero, prismatic card edges, GPU-feel motion) translate 1:1.
**Extract**:
- Gradient-mesh hero backgrounds (animated noise + radial blooms layered) — beats our flat radial bloom.
- **Prismatic 1px gradient borders** on cards (`border-image: linear-gradient(...) 1`).
- Diagonal section dividers cut at 6–8 deg with `clip-path`.
- Tight 4px scanline grid in product glamour shots.

### 3. Tesla — `getdesign.md/tesla`
**Why**: Sets the cinematic-hero rhythm we already lean on: huge typography, generous black, restrained accent. Best blueprint for our `/squeeze/` and `/jackpot/` hero slabs.
**Extract**:
- Single-stat hero with no decoration except the typography itself.
- Sticky scroll "spec strip" that reveals as you scroll (number + label + thin divider).
- Typographic widow control — manual `<br>` for headline cadence.
- Microcopy in 11px uppercase mono with tracked letter-spacing.

### 4. Linear — `getdesign.md/linear.app`
**Why**: The reference for premium dark UI chrome. Their command palette, keyboard hints, and toolbar treatment are the gold standard. Our scanner needs this discipline.
**Extract**:
- **⌘K command palette** with keyboard hints (`<kbd>` chips with subtle inner shadow).
- Tooltip with arrow + 8px radius + slight downward translate on hover.
- Translucent floating toolbar with `backdrop-filter: blur(20px) saturate(180%)`.
- Inline progress bars with diagonal hatching on incomplete state.

### 5. Stripe — `getdesign.md/stripe`
**Why**: The benchmark for animated gradient hero washes and "data feels alive" treatment. Their gradient mesh is the move — not flat radial blooms.
**Extract**:
- Animated gradient mesh hero (slow drift, multi-axis), beats our static `cy-bg::before`.
- Live shimmer on numeric counters (gradient sweep).
- Section transitions that fade colors between zones (zone color = section identity).
- Pill-shaped status indicators with pulsing dot.

---

## 5 Concrete CSS Upgrades

### Upgrade 1 — Animated gradient-mesh background (replaces flat radial bloom)
**File**: `cyber-shell.css` (replace `.cy-bg::before`)
**Page that benefits most**: `/jackpot/` (the hero needs more atmosphere)
```css
.cy-bg::before {
  content: "";
  position: absolute;
  inset: -20%;
  background:
    radial-gradient(900px 540px at 18% 8%, rgba(255, 42, 138, 0.18), transparent 65%),
    radial-gradient(720px 480px at 85% 18%, rgba(0, 255, 255, 0.14), transparent 65%),
    radial-gradient(1100px 700px at 50% 100%, rgba(176, 38, 255, 0.16), transparent 60%);
  animation: cy-mesh-drift 24s ease-in-out infinite alternate;
  filter: blur(40px) saturate(140%);
}
@keyframes cy-mesh-drift {
  0%   { transform: translate3d(0, 0, 0) scale(1); }
  50%  { transform: translate3d(2%, -1.5%, 0) scale(1.04); }
  100% { transform: translate3d(-1.5%, 1%, 0) scale(1.02); }
}
```

### Upgrade 2 — Prismatic gradient card border (NVIDIA)
**File**: `cyber-shell.css` (new utility)
**Page that benefits most**: `/scanner/` (every result card)
```css
.cy-prism-card {
  position: relative;
  background: rgba(10, 6, 28, 0.72);
  backdrop-filter: blur(14px);
  border-radius: 14px;
}
.cy-prism-card::before {
  content: "";
  position: absolute; inset: 0;
  padding: 1px; border-radius: inherit;
  background: linear-gradient(135deg, var(--cy-neon-cyan), var(--cy-neon-magenta) 50%, var(--cy-neon-purple));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
  pointer-events: none;
  opacity: 0.65;
  transition: opacity .25s ease;
}
.cy-prism-card:hover::before { opacity: 1; }
```

### Upgrade 3 — Shimmer sweep on colossal stats (Stripe)
**File**: `cinematic-hero.css` (extend `.cin-num`)
**Page that benefits most**: `/squeeze/` and `/cross-border/`
```css
.cy-neon-hero .cin-num {
  background: linear-gradient(110deg,
    #fff 0%, var(--cy-neon-cyan) 30%, #fff 50%, var(--cy-neon-magenta) 70%, #fff 100%);
  background-size: 300% 100%;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: cy-stat-shimmer 8s linear infinite;
}
@keyframes cy-stat-shimmer {
  from { background-position: 200% 0; }
  to   { background-position: -100% 0; }
}
```

### Upgrade 4 — Mission-readout strip (SpaceX)
**File**: `cyber-shell.css` (new component)
**Page that benefits most**: top of `/jackpot/`, `/defi/`, `/squeeze/`
```css
.cy-readout { display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 0; border: 1px solid rgba(0,255,255,.18);
  background: rgba(5,2,20,.55); backdrop-filter: blur(10px);
  font-family: "JetBrains Mono", ui-monospace, monospace; }
.cy-readout > div { padding: 14px 18px; border-right: 1px solid rgba(0,255,255,.10); }
.cy-readout > div:last-child { border-right: 0; }
.cy-readout .lbl { font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: #6a7ba0; }
.cy-readout .val { font: 700 22px/1 "Orbitron", sans-serif; color: var(--cy-neon-cyan);
  text-shadow: 0 0 10px rgba(0,255,255,.35); margin-top: 6px; }
.cy-readout .delta.up   { color: var(--cy-bull); }
.cy-readout .delta.down { color: var(--cy-bear); }
```

### Upgrade 5 — Diagonal scan-cut section divider (NVIDIA)
**File**: `cyber-shell.css` (new utility)
**Page that benefits most**: section breaks on `/cross-border/`, `/defi/`
```css
.cy-cut {
  position: relative; padding: clamp(64px, 9vw, 140px) 0;
  clip-path: polygon(0 4%, 100% 0, 100% 96%, 0 100%);
}
.cy-cut::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 1px;
  background: linear-gradient(90deg, transparent, var(--cy-neon-magenta), transparent);
  filter: blur(.5px);
}
```

---

## 3 New Components to Add

### A. Command Palette `cy-cmdk` (Linear / Raycast / Superhuman)
**Where**: global, but anchor on `/scanner/`. ⌘K pulls a translucent overlay listing tickers, filters, and saved screens. Add `<kbd>` chips with inset shadow, fuzzy match highlight in cyan, recent-history section. This single component makes the scanner feel like a tool, not a website.

### B. Telemetry Panel `cy-telemetry` (SpaceX mission control)
**Where**: top of `/jackpot/` and `/squeeze/`. A live stack of mono rows: `MARKET STATUS`, `TIME TO OPEN`, `VIX`, `BREADTH`, `CATALYSTS QUEUED`. Right-aligned values, slow blink on `LIVE` dot, occasional row flicker. Wires to the same data the email pipeline uses — zero new backend.

### C. Kinetic Ticker Headline `cy-kinetic` (RunwayML / ElevenLabs typography)
**Where**: hero of `/cross-border/` and `/defi/`. Headline letters cycle through a short character set (`A → ∆ → A`) on first paint, snap into final word — about 600ms. Scroll-trigger replay. Reuses Orbitron, no new fonts. Sells the "AI scanner" positioning the cyberpunk treatment is reaching for.
