import React, { useState } from 'react'

const SECTOR_LABELS = {
  tech: 'Technology',
  semis: 'Semiconductors',
  biotech: 'Biotech',
  financials: 'Financials',
  energy: 'Energy',
  materials: 'Materials',
  industrials: 'Industrials',
  consumer: 'Consumer',
  staples: 'Staples',
  comms: 'Communications',
  utilities: 'Utilities',
  real_estate: 'Real Estate',
}

const mono = "var(--font-mono, 'IBM Plex Mono', monospace)"

function sectionTitle(label) {
  return (
    <div style={{ marginBottom: 8, fontFamily: mono, fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--hud-muted)' }}>
      {label}
    </div>
  )
}

export default function ControlPanel({ filters, setFilters, sectors, totalNodes, filteredCount,
                                       sympathyDensityMode = 'full', sympathyLabelCount = 0,
                                       renderMode = 'cinematic', embedded = false }) {
  const [collapsed, setCollapsed] = useState(() => (
    embedded ? false : (typeof window !== 'undefined' ? window.innerWidth < 1760 : false)
  ))
  const isCollapsed = embedded ? false : collapsed
  const sympathyTone = sympathyDensityMode === 'suppressed'
    ? 'var(--hud-rose)'
    : sympathyDensityMode === 'grouped'
      ? 'var(--hud-gold)'
      : 'var(--hud-cyan)'
  const performanceSliceActive = filteredCount < totalNodes

  return (
    <div style={{
      position: embedded ? 'relative' : 'fixed',
      top: embedded ? 'auto' : 64,
      left: embedded ? 'auto' : 18,
      zIndex: embedded ? 'auto' : 220,
      width: embedded ? '100%' : (isCollapsed ? 58 : 286),
      height: embedded ? '100%' : 'auto',
      transition: embedded ? 'none' : 'width var(--motion-medium) var(--ease-authority)',
      overflow: embedded ? 'visible' : 'hidden',
    }}>
      {!embedded && (
        <button
          type="button"
          onClick={() => setCollapsed(c => !c)}
          style={{
            position: 'absolute',
            top: 10,
            right: 10,
            zIndex: 2,
            width: 34,
            height: 34,
            borderRadius: 999,
            border: '1px solid rgba(125,215,255,0.18)',
            background: 'rgba(6,14,24,0.9)',
            color: 'var(--hud-cyan)',
            fontFamily: mono,
            fontSize: 14,
            cursor: 'pointer',
            boxShadow: '0 0 18px rgba(114,229,255,0.08)',
          }}
          title={isCollapsed ? 'Expand controls' : 'Collapse controls'}
        >
          {isCollapsed ? '+' : '-'}
        </button>
      )}

      <div style={{
        background: embedded ? 'transparent' : 'var(--hud-panel-strong)',
        border: embedded ? 'none' : '1px solid var(--hud-border)',
        borderRadius: embedded ? 0 : 28,
        padding: isCollapsed ? '12px 10px' : (embedded ? '4px 2px 6px' : '18px 18px 16px'),
        backdropFilter: embedded ? 'none' : 'blur(24px)',
        boxShadow: embedded ? 'none' : '0 18px 52px rgba(0,0,0,0.42), inset 0 0 24px rgba(114,229,255,0.03)',
        color: 'var(--hud-text)',
        minHeight: embedded ? '100%' : 56,
        height: embedded ? '100%' : 'auto',
      }}>
        {!isCollapsed && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--hud-muted)' }}>
                  Tactical Controls
                </div>
                <div style={{ marginTop: 6, fontSize: 16, fontWeight: 700, letterSpacing: '-0.03em' }}>
                  Universe Slice
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--hud-muted)' }}>
                  Visible
                </div>
                <div style={{ marginTop: 6, fontFamily: mono, fontSize: 14, color: 'var(--hud-gold)' }}>
                  {filteredCount.toLocaleString()} / {totalNodes.toLocaleString()}
                </div>
                {performanceSliceActive && (
                  <div style={{ marginTop: 6, fontFamily: mono, fontSize: 8, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--hud-muted)' }}>
                    {renderMode} slice active
                  </div>
                )}
              </div>
            </div>

            {performanceSliceActive && (
              <div style={{
                marginBottom: 14,
                padding: '11px 12px',
                borderRadius: 16,
                background: 'rgba(114,229,255,0.05)',
                border: '1px solid rgba(114,229,255,0.12)',
                color: 'var(--hud-muted)',
                fontSize: 10,
                lineHeight: 1.6,
              }}>
                Rendering the highest-priority slice from the current universe scope to keep search, lock, and motion responsive under heavy market load.
              </div>
            )}

            <div style={{ display: 'grid', gap: 14 }}>
              <section style={{ padding: '14px 14px 12px', borderRadius: 18, background: 'rgba(11,23,35,0.74)', border: '1px solid rgba(134,162,191,0.12)' }}>
                {sectionTitle('Sector Lens')}
                <select
                  value={filters.sector}
                  onChange={e => setFilters(f => ({ ...f, sector: e.target.value }))}
                  style={{
                    width: '100%',
                    borderRadius: 14,
                    border: '1px solid rgba(125,215,255,0.18)',
                    background: 'rgba(8,18,29,0.92)',
                    color: filters.sector === 'ALL' ? 'var(--hud-muted)' : 'var(--hud-text)',
                    padding: '12px 14px',
                    outline: 'none',
                    fontFamily: mono,
                    fontSize: 12,
                    letterSpacing: '0.04em',
                    cursor: 'pointer',
                  }}
                >
                  <option value="ALL">All sectors</option>
                  {sectors.map(s => (
                    <option key={s} value={s}>
                      {SECTOR_LABELS[s] || s.toUpperCase()}
                    </option>
                  ))}
                </select>
              </section>

              <section style={{ padding: '14px 14px 12px', borderRadius: 18, background: 'rgba(11,23,35,0.74)', border: '1px solid rgba(134,162,191,0.12)' }}>
                {sectionTitle('Gravity Filter')}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontFamily: mono, fontSize: 11, color: 'var(--hud-muted)' }}>
                  <span>Minimum gravity</span>
                  <strong style={{ color: 'var(--hud-text)' }}>{filters.minGravity}</strong>
                </div>
                <input
                  type="range"
                  min={0}
                  max={80}
                  value={filters.minGravity}
                  onChange={e => setFilters(f => ({ ...f, minGravity: +e.target.value }))}
                  style={{ width: '100%', accentColor: 'var(--hud-gold)', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontFamily: mono, fontSize: 10, color: 'var(--hud-muted-2)' }}>
                  <span>Micro</span>
                  <span>Mid</span>
                  <span>Mega</span>
                </div>
              </section>

              <section style={{ padding: '14px 14px 12px', borderRadius: 18, background: 'rgba(11,23,35,0.74)', border: '1px solid rgba(134,162,191,0.12)' }}>
                {sectionTitle('Brightness Floor')}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontFamily: mono, fontSize: 11, color: 'var(--hud-muted)' }}>
                  <span>Minimum brightness</span>
                  <strong style={{ color: 'var(--hud-text)' }}>{filters.minBrightness}</strong>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={filters.minBrightness}
                  onChange={e => setFilters(f => ({ ...f, minBrightness: +e.target.value }))}
                  style={{ width: '100%', accentColor: 'var(--hud-cyan)', cursor: 'pointer' }}
                />
              </section>

              <label style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '14px 14px 12px',
                borderRadius: 18,
                background: filters.sparksOnly ? 'rgba(95,208,170,0.12)' : 'rgba(11,23,35,0.74)',
                border: `1px solid ${filters.sparksOnly ? 'rgba(95,208,170,0.34)' : 'rgba(134,162,191,0.12)'}`,
                cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={filters.sparksOnly}
                  onChange={e => setFilters(f => ({ ...f, sparksOnly: e.target.checked }))}
                  style={{ accentColor: 'var(--hud-emerald)', cursor: 'pointer' }}
                />
                <span style={{ fontFamily: mono, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: filters.sparksOnly ? 'var(--hud-emerald)' : 'var(--hud-text)' }}>
                  Active sparks only
                </span>
              </label>

              <section style={{ padding: '14px 14px 12px', borderRadius: 18, background: 'rgba(11,23,35,0.74)', border: '1px solid rgba(134,162,191,0.12)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  {sectionTitle('Sympathy Density')}
                  <span style={{ fontFamily: mono, fontSize: 10, color: sympathyTone, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                    {sympathyDensityMode}
                  </span>
                </div>
                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 0 4px',
                  cursor: 'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={filters.sympathyShield}
                    onChange={e => setFilters(f => ({ ...f, sympathyShield: e.target.checked }))}
                    style={{ accentColor: 'var(--hud-cyan)', cursor: 'pointer' }}
                  />
                  <span style={{ fontFamily: mono, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--hud-text)' }}>
                    High-density shield
                  </span>
                </label>
                <div style={{ marginTop: 8, fontSize: 10, color: 'var(--hud-muted)', lineHeight: 1.65 }}>
                  {sympathyLabelCount} live sympathy lane{sympathyLabelCount === 1 ? '' : 's'} tracked.
                  {filters.sympathyShield
                    ? ' Labels stay full in sparse scenes, group by sector once the field gets crowded, and collapse to selected/hover context only in high-density bursts.'
                    : ' All sympathy labels stay visible regardless of field density.'}
                </div>
              </section>
            </div>

            <button
              type="button"
              onClick={() => setFilters({ sector: 'ALL', minGravity: 1, minBrightness: 0, sparksOnly: false, sympathyShield: true })}
              style={{
                width: '100%',
                marginTop: 14,
                padding: '12px 14px',
                borderRadius: 16,
                border: '1px solid rgba(125,215,255,0.16)',
                background: 'rgba(8,18,29,0.82)',
                color: 'var(--hud-cyan)',
                fontFamily: mono,
                fontSize: 11,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              Reset filters
            </button>
          </>
        )}
      </div>
    </div>
  )
}
