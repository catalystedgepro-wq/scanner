export const HUD_FONTS = {
  display: '"Space Grotesk", "Avenir Next", "Segoe UI", sans-serif',
  mono: '"IBM Plex Mono", "SFMono-Regular", Consolas, monospace',
}

export const HUD_GLOBAL_STYLES = `
  @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;700&display=swap");

  :root {
    --hud-bg: #02040a;
    --hud-bg-alt: #050812;
    --hud-surface: rgba(10, 16, 26, 0.78);
    --hud-surface-strong: rgba(7, 13, 22, 0.92);
    --hud-surface-soft: rgba(14, 20, 31, 0.56);
    --hud-panel-strong: rgba(7, 13, 22, 0.82);
    --hud-panel-soft: rgba(9, 16, 28, 0.62);
    --hud-border: rgba(215, 180, 106, 0.18);
    --hud-border-strong: rgba(215, 180, 106, 0.34);
    --hud-line: rgba(114, 229, 255, 0.14);
    --hud-text: #f5efe4;
    --hud-muted: #9ea8ba;
    --hud-muted-2: rgba(158, 168, 186, 0.66);
    --hud-muted-strong: #cab895;
    --hud-gold: #d7b46a;
    --hud-gold-soft: #8d6b38;
    --hud-cyan: #72e5ff;
    --hud-teal: #2ad4c5;
    --hud-magenta: #d59cff;
    --hud-success: #7fe8b3;
    --hud-emerald: #66f5cf;
    --hud-warning: #ffbf69;
    --hud-danger: #ff8686;
    --hud-rose: #ff728f;
    --hud-amber: #f7c76f;
    --hud-shadow: 0 18px 48px rgba(0, 0, 0, 0.44);
    --motion-medium: 320ms;
    --ease-authority: cubic-bezier(0.16, 0.84, 0.22, 1);
  }

  * { box-sizing: border-box; }

  html, body, #root {
    width: 100%;
    min-height: 100%;
    margin: 0;
  }

  body {
    color: var(--hud-text);
    font-family: ${HUD_FONTS.display};
    background:
      radial-gradient(circle at 50% 50%, rgba(138, 227, 255, 0.11), transparent 18%),
      radial-gradient(circle at 52% 48%, rgba(170, 146, 255, 0.07), transparent 26%),
      linear-gradient(180deg, rgba(2, 5, 12, 0.86) 0%, rgba(3, 8, 18, 0.72) 42%, rgba(4, 9, 18, 0.9) 100%),
      url('/hud-space-bg.png') center center / cover no-repeat fixed;
    overflow-x: hidden;
  }

  body::before {
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
      radial-gradient(circle at 50% 50%, rgba(255,255,255,0.045) 0%, transparent 38%),
      radial-gradient(circle at 50% 50%, rgba(7, 11, 22, 0) 44%, rgba(3, 5, 12, 0.34) 100%);
    mix-blend-mode: screen;
    opacity: 0.08;
  }

  body::after {
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(180deg, rgba(255,255,255,0.028) 0%, transparent 18%, transparent 82%, rgba(255,255,255,0.02) 100%),
      radial-gradient(circle at center, rgba(96, 183, 255, 0.04) 0%, transparent 46%);
    mix-blend-mode: screen;
    opacity: 0.06;
  }

  #root::before {
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    background: none;
    opacity: 0;
  }

  button, input, select {
    font: inherit;
  }
`;

export function glassPanel(accent = 'rgba(215, 180, 106, 0.24)', glow = 'rgba(215, 180, 106, 0.12)') {
  return {
    background: 'linear-gradient(180deg, rgba(8, 15, 25, 0.84) 0%, rgba(5, 9, 17, 0.64) 100%)',
    border: `1px solid ${accent}`,
    boxShadow: `0 24px 64px rgba(0, 0, 0, 0.42), 0 0 28px ${glow}, inset 0 1px 0 rgba(255,255,255,0.05), inset 0 0 0 1px rgba(255,255,255,0.02)`,
    backdropFilter: 'blur(18px) saturate(1.16)',
    WebkitBackdropFilter: 'blur(18px) saturate(1.16)',
  }
}

export const monoLabel = {
  fontFamily: HUD_FONTS.mono,
  letterSpacing: '0.24em',
  textTransform: 'uppercase',
}

export const goldDivider = {
  height: 1,
  background: 'linear-gradient(90deg, rgba(215,180,106,0) 0%, rgba(215,180,106,0.26) 24%, rgba(114,229,255,0.18) 76%, rgba(114,229,255,0) 100%)',
}
