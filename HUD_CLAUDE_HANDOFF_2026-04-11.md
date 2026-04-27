# Claude Handoff: Cerebro HUD Shell Failure

## Situation

The operator asked for a bulletproof decoupled top deck on the live HUD at [67.205.148.181](http://67.205.148.181), plus a more fluid graph experience overall.

I applied the requested top-deck structure exactly in:

- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx#L4296)

The exact inserted surfaces are:

- permanent fixed handle at [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx#L4296)
- fixed telemetry card at [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx#L4306)

Build passed and deploy succeeded. Live bundle now includes:

- `assets/index--_zevnKs.js`

## What Actually Happened

The class-based decoupled top deck compiled, but it does **not** render correctly on the live HUD.

Live evidence:

- screenshot: [hud-broken-live.png](/home/operator/.openclaw/workspace/output/playwright/hud-broken-live.png)
- the top handle is not visible
- the top telemetry card is not visible
- left and right rail handles are visible
- the graph canvas is visible
- the page no longer has the old invisible-cloak problem, but the top deck is effectively gone

## Why This Likely Failed

This HUD is not behaving like a reliable Tailwind runtime for critical shell positioning.

The inserted top-deck architecture relies on utility classes for:

- `fixed`
- `top-0`
- `left-1/2`
- `-translate-x-1/2`
- `w-48 h-6`
- `z-[60]`
- `top-8`
- `w-[90%]`
- `max-w-6xl`

The earlier shell bugs already showed that critical HUD layout surfaces were safer when hard-pinned with inline styles instead of utility-only positioning.

So the most likely root cause is:

- the HUD build/runtime is not consistently honoring these utility classes for critical fixed-position shell elements
- as a result, the exact requested JSX exists in source, but the handle/card do not paint in production as expected

## Current Code State

Top deck in source currently matches the requested pattern:

- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx#L4296)

Other relevant files:

- [liquid-glass-card.tsx](/home/operator/.openclaw/workspace/hud/src/components/ui/liquid-glass-card.tsx)
- [bento-grid.tsx](/home/operator/.openclaw/workspace/hud/src/components/ui/bento-grid.tsx)

## Recommended Next Move For Claude

Do **not** keep iterating on the top deck with utility-class-only positioning.

Instead:

1. Keep the current JSX structure conceptually.
2. Replace the top handle and top telemetry wrapper with explicit inline styles for:
   - `position: fixed`
   - `top`
   - `left`
   - `transform`
   - `width`
   - `height`
   - `zIndex`
   - `display/flex`
3. Leave the inner telemetry content alone.
4. Verify live rendering with Playwright screenshot, not DOM assumptions.

## Remaining Operator Expectations

These are still the target outcomes:

- top, left, and right decks must load fully inside the viewport
- no invisible cloak over the graph canvas
- ultra-transparent liquid glass for decks
- remove any leftover lock annotation / lock sticker language
- more fluid connector behavior
- more seamless zoom and node centering on click

## Deployment / Verification Commands

Build:

```bash
cd /home/operator/.openclaw/workspace/hud
npm run build
```

Deploy:

```bash
cd /home/operator/.openclaw/workspace
bash ops/deploy_cerebro_droplet.sh --stage-only
```

Probe:

```bash
cd /home/operator/.openclaw/workspace
node tmp_hud_probe.cjs
```

## Blunt Summary

The top-deck request was implemented exactly in source, but the live HUD still fails visually because this shell cannot be trusted to honor utility-only positioning for critical chrome. The next solver should hard-pin the top handle and top deck with inline layout styles and verify with screenshots immediately after deploy.
