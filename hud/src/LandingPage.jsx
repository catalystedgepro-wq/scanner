import React from 'react'

const mono = "var(--font-mono, 'IBM Plex Mono', monospace)"
const display = "var(--font-display, 'Space Grotesk', sans-serif)"

const operatorCards = [
  {
    kicker: 'Sympathy Web',
    title: 'Watch contagion, not isolated tickers',
    body: 'Sector gravity, ETF tethering, and spark propagation turn the market into a map instead of a list.',
  },
  {
    kicker: 'Trust Layer',
    title: 'Keep verified filings separate from inferred signals',
    body: 'Operator surfaces should always tell you whether a claim is verified, inferred, or still pending review.',
  },
  {
    kicker: 'Cadence',
    title: 'Premarket first. Intraday when it matters.',
    body: 'The Scanner publishes the core build before the desk opens, then rolls forward on a controlled market-hours cadence.',
  },
]

const valueCards = [
  {
    label: 'Desk Objective',
    title: 'Find attention before it becomes consensus',
    body: 'Cerebro is a tactical operator surface for catalyst traders, not a generic finance dashboard.',
  },
  {
    label: 'Intelligence Inputs',
    title: 'Filing context, crowding, sympathy, macro pressure',
    body: 'The stack becomes useful when the operator can see the why, the transmission path, and the timing window at once.',
  },
  {
    label: 'User Mode',
    title: 'High-clarity command center, low-noise workflow',
    body: 'The interface should feel like a tier-one tactical console: calm hierarchy, disciplined color, and readable motion.',
  },
  {
    label: 'Execution Surface',
    title: 'Scanner for discovery. HUD for topology.',
    body: 'The public page scouts opportunities. The HUD is where the operator interrogates the system and decides what matters.',
  },
]

function chip(text) {
  return (
    <span key={text} className="cerebro-chip">
      {text}
    </span>
  )
}

export default function LandingPage({ onLaunch }) {
  return (
    <div className="cerebro-screen" style={{ minHeight: '100vh', color: 'var(--hud-text)', fontFamily: display, overflowX: 'hidden' }}>
      <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none', background: 'radial-gradient(circle at 50% 18%, rgba(125,215,255,0.12), transparent 30%), radial-gradient(circle at 50% 100%, rgba(95,208,170,0.08), transparent 28%)' }} />

      <nav style={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 24,
        padding: '18px 28px',
        borderBottom: '1px solid rgba(134,162,191,0.12)',
        background: 'rgba(7,17,27,0.84)',
        backdropFilter: 'blur(18px)',
      }}>
        <div>
          <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.26em', textTransform: 'uppercase', color: 'var(--hud-muted)' }}>
            Cerebro / Catalyst Edge
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>
            Tactical Intelligence Stack
          </div>
        </div>
        <div style={{ fontFamily: mono, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--hud-muted)' }}>
          Verified filings. Live topology. Operator workflow.
        </div>
      </nav>

      <main style={{ maxWidth: 1320, margin: '0 auto', padding: '42px 24px 56px' }}>
        <section style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.28fr) minmax(320px, 0.92fr)', gap: 22, alignItems: 'stretch' }}>
          <div className="cerebro-glass" style={{ borderRadius: 28, padding: '30px 30px 28px', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', background: 'linear-gradient(135deg, rgba(125,215,255,0.12), transparent 42%), radial-gradient(circle at 88% 12%, rgba(231,183,108,0.18), transparent 22%)' }} />
            <div style={{ position: 'relative', zIndex: 1 }}>
              <div className="cerebro-kicker">Operator Surface</div>
              <h1 style={{ margin: '14px 0 18px', maxWidth: '11ch', fontSize: 'clamp(48px, 8vw, 88px)', lineHeight: 0.96, letterSpacing: '-0.05em' }}>
                Trade the <span style={{ color: 'var(--hud-gold)' }}>catalyst window</span> before it becomes consensus.
              </h1>
              <p style={{ maxWidth: 760, margin: 0, color: 'var(--hud-muted)', fontSize: 18, lineHeight: 1.72 }}>
                Scanner is the public discovery desk. The HUD is the topology engine. Together they tell you what happened, how it spreads, and whether the evidence is verified or still inferred.
              </p>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 22 }}>
                {[
                  'Verified filing context',
                  'Intraday refresh discipline',
                  'Sympathy-aware topology',
                ].map(chip)}
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 28 }}>
                <button
                  onClick={onLaunch}
                  style={{
                    padding: '16px 22px',
                    borderRadius: 16,
                    border: '1px solid rgba(231,183,108,0.42)',
                    background: 'linear-gradient(135deg, rgba(231,183,108,0.96), rgba(247,212,156,0.92))',
                    color: '#07111b',
                    fontFamily: mono,
                    fontSize: 12,
                    fontWeight: 600,
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                    boxShadow: '0 20px 34px rgba(231,183,108,0.18)',
                  }}
                >
                  Launch HUD
                </button>
                <button
                  type="button"
                  style={{
                    padding: '16px 22px',
                    borderRadius: 16,
                    border: '1px solid rgba(125,215,255,0.24)',
                    background: 'rgba(9,21,33,0.72)',
                    color: 'var(--hud-cyan)',
                    fontFamily: mono,
                    fontSize: 12,
                    letterSpacing: '0.18em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                  }}
                >
                  Read Workflow
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginTop: 28 }}>
                {[
                  ['Signal classes', 'Filing, options, sympathy, macro'],
                  ['Operator promise', 'Tell the user what is verified'],
                  ['Visual mode', 'Tier-one tactical desk, not retail clutter'],
                ].map(([label, value]) => (
                  <div key={label} style={{ background: 'rgba(12,24,36,0.72)', border: '1px solid rgba(134,162,191,0.14)', borderRadius: 18, padding: '14px 16px' }}>
                    <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--hud-muted-2)' }}>{label}</div>
                    <div style={{ marginTop: 8, fontSize: 15, lineHeight: 1.55 }}>{value}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 18 }}>
            {operatorCards.map(card => (
              <article key={card.title} className="cerebro-glass" style={{ borderRadius: 24, padding: '22px 22px 20px', background: 'var(--hud-panel-soft)' }}>
                <div className="cerebro-kicker">{card.kicker}</div>
                <h2 style={{ margin: '12px 0 10px', fontSize: 24, lineHeight: 1.1, letterSpacing: '-0.03em' }}>{card.title}</h2>
                <p style={{ margin: 0, color: 'var(--hud-muted)', fontSize: 15, lineHeight: 1.7 }}>{card.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section style={{ marginTop: 26, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 18 }}>
          {valueCards.map(card => (
            <article key={card.title} className="cerebro-glass" style={{ borderRadius: 22, padding: '20px 20px 18px', minHeight: 220 }}>
              <div className="cerebro-kicker">{card.label}</div>
              <h3 style={{ margin: '14px 0 10px', fontSize: 22, lineHeight: 1.14, letterSpacing: '-0.03em' }}>{card.title}</h3>
              <p style={{ margin: 0, color: 'var(--hud-muted)', fontSize: 15, lineHeight: 1.68 }}>{card.body}</p>
            </article>
          ))}
        </section>
      </main>
    </div>
  )
}
