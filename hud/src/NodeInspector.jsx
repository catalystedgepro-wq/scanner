import React, { useEffect, useState } from 'react'
import { HUD_FONTS, glassPanel, monoLabel, goldDivider } from './theme.js'

const API_BASE = ''   // relative — Nginx proxies /api/ → FastAPI port 8000

const SECTOR_COLORS = {
  tech: '#00d4ff', semis: '#7c3aed', biotech: '#10b981',
  financials: '#f59e0b', energy: '#ef4444', materials: '#84cc16',
  industrials: '#6366f1', consumer: '#f97316', staples: '#14b8a6',
  comms: '#ec4899', utilities: '#8b5cf6', real_estate: '#d97706',
}

function VelocityBar({ label, value, color, max = 20 }) {
  if (!value || value === 0) return null
  const pct = Math.min(Math.abs(value) / max * 100, 100)
  const positive = value > 0
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 10, color: 'var(--hud-muted)', fontFamily: HUD_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
        <span>{label}</span>
        <b style={{ color: positive ? color : 'var(--hud-danger)' }}>
          {positive ? '+' : ''}{value.toFixed(2)}v
        </b>
      </div>
      <div style={{ height: 5, background: 'rgba(0,0,0,0.45)', borderRadius: 999, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: positive
            ? 'linear-gradient(90deg, rgba(114,229,255,0.88), rgba(42,212,197,0.92))'
            : 'linear-gradient(90deg, rgba(255,134,134,0.88), rgba(255,191,105,0.9))',
          borderRadius: 999,
          boxShadow: `0 0 18px ${positive ? 'rgba(114,229,255,0.22)' : 'rgba(255,134,134,0.22)'}`,
          transition: 'width 0.4s ease',
        }} />
      </div>
    </div>
  )
}

const CATALYST_COLORS = {
  REVENUE_BEAT:    '#10b981',
  PRODUCT_LAUNCH:  '#00d4ff',
  ACQUISITION:     '#a855f7',
  LEGAL_RISK:      '#ef4444',
  DILUTION_RISK:   '#f97316',
  INSIDER_BUY:     '#00ffcc',
  DEBT_RESTRUCTURE:'#f59e0b',
  GUIDANCE_RAISE:  '#10b981',
  GUIDANCE_CUT:    '#ef4444',
  PARTNERSHIP:     '#6366f1',
  REGULATORY:      '#f59e0b',
  UNKNOWN:         '#334455',
}

function NeuralScanBar() {
  return (
    <div style={{ marginBottom: 8, padding: '10px 12px', borderRadius: 14, background: 'rgba(114,229,255,0.04)', border: '1px solid rgba(114,229,255,0.12)' }}>
      <div style={{ ...monoLabel, fontSize: 9, color: 'var(--hud-muted-strong)', marginBottom: 6 }}>
        neural scan
      </div>
      <div style={{ height: 3, background: 'rgba(255,255,255,0.05)', borderRadius: 999, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: '40%',
          background: 'linear-gradient(90deg, transparent, var(--hud-cyan), transparent)',
          animation: 'neuralScan 1.6s ease-in-out infinite',
          borderRadius: 999,
        }} />
      </div>
      <div style={{ fontSize: 10, color: 'var(--hud-muted)', marginTop: 6, letterSpacing: '0.04em' }}>
        Reading filing context and classifying trust state...
      </div>
    </div>
  )
}

function formatSectorLabel(sector = '') {
  const normalized = String(sector || '').replace(/_/g, ' ').trim()
  if (!normalized) return 'GENERAL'
  return normalized.toUpperCase()
}

export default function NodeInspector({
  node,
  sympathyLead = null,
  sympathyPeers = [],
  visitHistory = [],
  onJumpTo = null,
  onClose,
  inline = false,
}) {
  const jump = (ticker) => {
    if (!ticker || ticker === node?.id) return
    if (typeof onJumpTo === 'function') onJumpTo(ticker)
  }
  const [detail,    setDetail]    = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [aiData,    setAiData]    = useState(null)   // { summary, confidence, catalyst_type, filing_type, filing_date, model_metadata }
  const [aiLoading, setAiLoading] = useState(false)

  useEffect(() => {
    if (!node) { setDetail(null); setAiData(null); return }
    setLoading(true)
    fetch(`${API_BASE}/api/ticker/${node.id}`)
      .then(r => r.json())
      .then(d => { setDetail(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [node?.id])

  // AI summary — fetches from /api/ai-summary/:ticker
  // 404 = endpoint not yet live; shows "analysis pending" gracefully
  useEffect(() => {
    if (!node) { setAiData(null); return }
    setAiLoading(true)
    setAiData(null)
    fetch(`${API_BASE}/api/ai-summary/${node.id}`)
      .then(r => {
        if (!r.ok) throw new Error(r.status)
        return r.json()
      })
      .then(d => { setAiData(d); setAiLoading(false) })
      .catch(() => { setAiData({ pending: true }); setAiLoading(false) })
  }, [node?.id])

  if (!node) return null

  const velocityEvent = detail?.velocity_event || node.velocityEvent || null
  const sparks   = detail?.sparks || node.sparks || {}
  const totalVel = Number(velocityEvent?.total_velocity ?? (
    (sparks.patent || 0) + (sparks.legal || 0) +
    (sparks.digital || 0) + (sparks.options || 0) + (sparks.weather || 0)
  ))
  const sectorColor = SECTOR_COLORS[node.sector] || '#374151'
  const gics = detail?.gics || {}
  const modelMetadata = aiData?.model_metadata || null
  const sourceTone = aiData?.source === 'verified_fallback'
    ? { label: 'verified filing context', accent: 'var(--hud-cyan)', bg: 'rgba(114,229,255,0.08)', border: 'rgba(114,229,255,0.18)' }
    : aiData?.source === 'unverified_fallback'
      ? { label: 'review required', accent: 'var(--hud-warning)', bg: 'rgba(255,191,105,0.08)', border: 'rgba(255,191,105,0.22)' }
      : aiData?.pending
        ? { label: 'endpoint pending', accent: 'var(--hud-muted)', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.08)' }
        : { label: 'model synthesis', accent: 'var(--hud-gold)', bg: 'rgba(215,180,106,0.08)', border: 'rgba(215,180,106,0.18)' }
  const modelTone = aiData?.pending
    ? { color: 'rgba(158,168,186,0.82)', bg: 'rgba(255,255,255,0.03)', border: 'rgba(255,255,255,0.06)' }
    : modelMetadata?.is_fallback
      ? { color: 'var(--hud-warning)', bg: 'rgba(255,191,105,0.08)', border: 'rgba(255,191,105,0.18)' }
      : { color: 'var(--hud-cyan)', bg: 'rgba(114,229,255,0.08)', border: 'rgba(114,229,255,0.16)' }
  const modelLabel = aiData?.pending
    ? 'endpoint offline'
    : modelMetadata?.display_name || (modelMetadata?.is_fallback ? 'fallback path' : 'model offline')
  const sympathyHistory = aiData?.sympathy_history || detail?.sympathy_history || []
  const memoryContext = aiData?.memory_context || detail?.memory_context || []
  const scannerOnly = Boolean(detail?.scanner_only ?? node.scanner_only)
  const scannerSources = detail?.scanner_sources || node.scanner_sources || []
  const scannerRank = detail?.scanner_rank ?? node.scanner_rank ?? null
  const scannerScore = detail?.scanner_score ?? node.scanner_score ?? null
  const scannerForm = detail?.scanner_form || node.scanner_form || ''
  const scannerTags = detail?.scanner_tags || node.scanner_tags || ''
  const scannerLink = detail?.scanner_link || node.scanner_link || ''
  const sectorSource = detail?.sector_source || node.sector_source || 'unknown'
  const sectorInferred = Boolean(detail?.sector_inferred ?? node.sector_inferred)
  const sectorEvidence = detail?.sector_evidence || node.sector_evidence || ''
  const latestSympathy = sympathyHistory[0] || null
  const liveSympathyLead = sympathyLead || node.sympathyLead || null
  const sympathyLeadTicker = liveSympathyLead?.leader
    || (latestSympathy?.relation === 'trigger' ? node.id : latestSympathy?.trigger_ticker)
    || ''
  const sympathyLeadSector = liveSympathyLead?.sector || latestSympathy?.sector || node.sector || ''
  const sympathyLeadRole = liveSympathyLead?.role || latestSympathy?.relation || ''
  const sympathyLeadSummary = sympathyLeadTicker
    ? sympathyLeadRole === 'leader'
      ? `${sympathyLeadTicker} is currently pulling ${formatSectorLabel(sympathyLeadSector)} peers through the active sympathy rail.`
      : `This move is tracking ${sympathyLeadTicker} through the ${formatSectorLabel(sympathyLeadSector)} sympathy rail.`
    : ''

  const posStyle = inline
    ? { position: 'relative', width: '100%', maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }
    : { position: 'fixed', top: 48, right: 16, zIndex: 200, width: 300, maxHeight: 'calc(100vh - 100px)', overflowY: 'auto' }

  return (
    <div style={{
      ...posStyle,
      ...glassPanel(`${sectorColor}44`, `${sectorColor}16`),
      borderRadius: 24, padding: 20,
      fontFamily: HUD_FONTS.display,
      animation: 'slideIn 0.2s ease',
    }}>
      <style>{`
        @keyframes slideIn   { from { opacity:0; transform:translateX(20px); } to { opacity:1; transform:translateX(0); } }
        @keyframes pulse     { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
        @keyframes neuralScan { 0% { transform:translateX(-100%); } 100% { transform:translateX(350%); } }
        @keyframes aiFadeIn  { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(0,212,255,0.2); border-radius: 2px; }
      `}</style>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14, paddingBottom: 12, borderBottom: `1px solid ${sectorColor}33` }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: node.is_rogue ? 'var(--hud-magenta)' : 'var(--hud-cyan)', letterSpacing: '-0.04em', lineHeight: 1, fontFamily: HUD_FONTS.display }}>
              {node.id}
            </div>
            {node.is_rogue && (
              <span style={{
                fontSize: 8, fontWeight: 700, letterSpacing: 2, padding: '2px 6px',
                background: 'rgba(255,0,255,0.12)', border: '1px solid rgba(255,0,255,0.4)',
                borderRadius: 3, color: '#ff00ff', textTransform: 'uppercase',
                animation: 'pulse 1.5s ease infinite',
              }}>
                ROGUE NODE
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: 'var(--hud-muted)', marginTop: 6, maxWidth: 220, lineHeight: 1.55 }}>
            {node.name}
          </div>
        </div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: '#334455', fontSize: 16, padding: 4, lineHeight: 1,
          transition: 'color 0.2s',
        }}
          onMouseOver={e => e.target.style.color = '#fff'}
          onMouseOut={e => e.target.style.color = '#334455'}
        >✕</button>
      </div>

      {/* ── Recent-visit breadcrumb chips ── */}
      {Array.isArray(visitHistory) && visitHistory.length > 1 && (
        <div style={{ marginBottom: 14, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
          <span style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-muted-strong)', marginRight: 2 }}>
            recent
          </span>
          {visitHistory.slice(0, 6).map((tk, idx) => {
            const isCurrent = tk === node?.id
            return (
              <button
                key={`${tk}-${idx}`}
                type="button"
                onClick={() => jump(tk)}
                disabled={isCurrent || !onJumpTo}
                title={isCurrent ? `${tk} (current)` : `Jump back to ${tk}`}
                style={{
                  fontFamily: HUD_FONTS.mono,
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  padding: '3px 8px',
                  borderRadius: 999,
                  cursor: isCurrent || !onJumpTo ? 'default' : 'pointer',
                  color: isCurrent ? 'var(--hud-gold)' : 'var(--hud-muted-strong)',
                  background: isCurrent ? 'rgba(215,180,106,0.1)' : 'rgba(255,255,255,0.04)',
                  border: isCurrent ? '1px solid rgba(215,180,106,0.3)' : '1px solid rgba(255,255,255,0.08)',
                  opacity: isCurrent ? 1 : 0.85,
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => {
                  if (!isCurrent && onJumpTo) {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.1)'
                    e.currentTarget.style.color = 'var(--hud-text)'
                  }
                }}
                onMouseLeave={e => {
                  if (!isCurrent && onJumpTo) {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
                    e.currentTarget.style.color = 'var(--hud-muted-strong)'
                  }
                }}
              >
                {tk}
              </button>
            )
          })}
        </div>
      )}

      {loading && (
        <div style={{ color: '#334455', fontSize: 11, textAlign: 'center', padding: '20px 0' }}>
          Loading intelligence...
        </div>
      )}

      {(scannerOnly || scannerSources.length > 0) && (
        <div style={{
          marginBottom: 16,
          padding: '12px 14px',
          borderRadius: 16,
          background: scannerOnly ? 'rgba(215,180,106,0.08)' : 'rgba(114,229,255,0.05)',
          border: scannerOnly ? '1px solid rgba(215,180,106,0.2)' : '1px solid rgba(114,229,255,0.14)',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.03)',
        }}>
          <div style={{ ...monoLabel, fontSize: 8, color: scannerOnly ? 'var(--hud-gold)' : 'var(--hud-cyan)', marginBottom: 8 }}>
            scanner parity
          </div>
          <div style={{ color: 'var(--hud-text)', fontSize: 11, lineHeight: 1.6 }}>
            {scannerOnly
              ? 'This pick is entering Cerebro through the scanner parity bridge and is still awaiting full entity_master mapping.'
              : 'This node is represented in both the scanner and the mapped Cerebro universe.'}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
            {scannerSources.map(source => (
              <span key={source} style={{
                padding: '4px 8px',
                borderRadius: 999,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.08)',
                color: 'var(--hud-muted-strong)',
                fontSize: 8,
                fontFamily: HUD_FONTS.mono,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
              }}>
                {source}
              </span>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, marginTop: 10 }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '8px 10px' }}>
              <div style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-muted)' }}>scanner rank</div>
              <div style={{ color: 'var(--hud-text)', fontSize: 13, fontWeight: 700 }}>{scannerRank ?? '—'}</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '8px 10px' }}>
              <div style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-muted)' }}>scanner score</div>
              <div style={{ color: 'var(--hud-text)', fontSize: 13, fontWeight: 700 }}>
                {scannerScore != null ? Number(scannerScore).toFixed(2) : '—'}
              </div>
            </div>
          </div>

          {(scannerForm || scannerTags) && (
            <div style={{ marginTop: 10, fontSize: 10, color: 'var(--hud-muted)', lineHeight: 1.65 }}>
              {scannerForm ? <div>Form: <b style={{ color: 'var(--hud-text)' }}>{scannerForm}</b></div> : null}
              {scannerTags ? <div>Signals: {scannerTags}</div> : null}
            </div>
          )}

          {scannerLink && (
            <div style={{ marginTop: 10 }}>
              <a
                href={scannerLink}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: 10, color: 'var(--hud-gold)', textDecoration: 'none', letterSpacing: '0.08em' }}
              >
                ↗ Scanner source filing
              </a>
            </div>
          )}
        </div>
      )}

      {/* Bedrock metrics */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 9, color: '#334455', letterSpacing: 2, marginBottom: 10, textTransform: 'uppercase' }}>
          Static Bedrock
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {[
            { label: 'Gravity',    value: (detail?.gravity   || node.gravity  || 0).toFixed(2), color: '#6366f1' },
            { label: 'Brightness', value: (detail?.brightness|| node.brightness||0).toFixed(2), color: '#00ffcc' },
            { label: 'Cap Tier',   value: (detail?.cap_tier  || node.cap_tier || '—').toUpperCase(), color: '#f59e0b' },
            { label: 'ETF Weight', value: detail?.etf_weights_sum ? detail.etf_weights_sum.toFixed(4) : '—', color: '#8b5cf6' },
          ].map(m => (
            <div key={m.label} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 5, padding: '8px 10px' }}>
              <div style={{ fontSize: 9, color: '#445566', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 3 }}>{m.label}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: m.color }}>{m.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Sector / GICS */}
      <div style={{ marginBottom: 16, padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 16, borderLeft: `3px solid ${sectorColor}`, boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.03)' }}>
        <div style={{ ...monoLabel, fontSize: 9, color: 'var(--hud-muted)', marginBottom: 6 }}>GICS classification</div>
        <div style={{ color: sectorColor, fontWeight: 700, fontSize: 12 }}>
          {node.sector?.toUpperCase() || 'UNCLASSIFIED'}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          <span style={{
            fontSize: 9,
            padding: '4px 7px',
            borderRadius: 999,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            fontFamily: HUD_FONTS.mono,
            color: sectorInferred ? 'var(--hud-warning)' : 'var(--hud-cyan)',
            border: `1px solid ${sectorInferred ? 'rgba(255,191,105,0.24)' : 'rgba(114,229,255,0.18)'}`,
            background: sectorInferred ? 'rgba(255,191,105,0.08)' : 'rgba(114,229,255,0.06)',
          }}>
            {sectorInferred ? 'Inferred sector' : sectorSource === 'gics' ? 'Direct GICS' : sectorSource.replace(/_/g, ' ')}
          </span>
          {sectorEvidence ? (
            <span style={{
              fontSize: 9,
              padding: '4px 7px',
              borderRadius: 999,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              fontFamily: HUD_FONTS.mono,
              color: 'var(--hud-muted-strong)',
              border: '1px solid rgba(215,180,106,0.18)',
              background: 'rgba(215,180,106,0.06)',
            }}>
              via {sectorEvidence}
            </span>
          ) : null}
        </div>
        {gics.i && <div style={{ color: '#556677', fontSize: 10, marginTop: 2 }}>{gics.i}</div>}
        {gics.si && <div style={{ color: '#445566', fontSize: 10 }}>{gics.si}</div>}
      </div>

      {/* ETF Canopy / Rogue Node */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 9, color: '#334455', letterSpacing: 2, marginBottom: 8, textTransform: 'uppercase' }}>
          ETF Canopy
        </div>

        {node.is_rogue ? (
          <div style={{
            padding: '10px 12px',
            background: 'rgba(255,0,255,0.06)',
            border: '1px solid rgba(255,0,255,0.25)',
            borderRadius: 5,
          }}>
            <div style={{ color: '#ff00ff', fontWeight: 700, fontSize: 11, letterSpacing: 1, marginBottom: 4 }}>
              ⚡ ZERO ETF TETHERS
            </div>
            <div style={{ color: '#886688', fontSize: 10, lineHeight: 1.5 }}>
              No institutional ETF includes this node. When a velocity spark hits, it moves purely on its own fundamentals — unchained from $SPY or $QQQ drag. Pure catalyst play.
            </div>
          </div>
        ) : node.etf_overlords?.length > 0 ? (
          <div>
            {node.etf_overlords.map((e, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '5px 8px', marginBottom: 4,
                background: 'rgba(68,102,255,0.06)',
                border: '1px solid rgba(68,102,255,0.18)',
                borderRadius: 4,
              }}>
                <span style={{ color: '#8899cc', fontSize: 11, fontWeight: 700, letterSpacing: 1 }}>
                  ${e.etf}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{
                    height: 3, width: Math.min(Math.max((e.weight || 0) * 4, 4), 60),
                    background: '#4466ff', borderRadius: 2,
                    boxShadow: '0 0 4px #4466ff88',
                  }} />
                  <span style={{ color: '#4466ff', fontSize: 10 }}>
                    {(e.weight || 0).toFixed(2)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: '#2a3a4a', fontSize: 10, fontStyle: 'italic', padding: '8px 0' }}>
            ETF canopy pending — bedrock sweep in progress
          </div>
        )}
      </div>

      {/* Velocity / Sparks */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ fontSize: 9, color: '#334455', letterSpacing: 2, textTransform: 'uppercase' }}>
            Velocity Sparks
          </div>
          {totalVel !== 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '2px 8px',
                borderRadius: 10, background: totalVel > 0 ? 'rgba(0,255,204,0.12)' : 'rgba(239,68,68,0.12)',
                color: totalVel > 0 ? '#00ffcc' : '#ef4444',
                animation: 'pulse 2s infinite',
              }}>
                {totalVel > 0 ? '+' : ''}{totalVel.toFixed(2)}v TOTAL
              </span>
              {velocityEvent?.severity && (
                <span style={{
                  fontSize: 8, fontWeight: 700, padding: '3px 8px',
                  borderRadius: 999, border: '1px solid rgba(255,255,255,0.08)',
                  background: 'rgba(255,255,255,0.04)', color: '#cbd5e1',
                  letterSpacing: 1, textTransform: 'uppercase',
                }}>
                  {velocityEvent.severity}
                </span>
              )}
            </div>
          )}
        </div>

        {totalVel === 0 ? (
          <div style={{ color: '#2a3a4a', fontSize: 11, fontStyle: 'italic', padding: '12px 0' }}>
            No active velocity injections — node dormant
          </div>
        ) : (
          <>
            <VelocityBar label="Options Flow"   value={sparks.options || 0} color="#f59e0b" />
            <VelocityBar label="Digital Buzz"   value={sparks.digital || 0} color="#00d4ff" />
            <VelocityBar label="Patent Spark"   value={sparks.patent  || 0} color="#7c3aed" />
            <VelocityBar label="Legal Risk"     value={sparks.legal   || 0} color="#ef4444" />
            <VelocityBar label="Weather Shock"  value={sparks.weather || 0} color="#10b981" />
            {sparks.digital_signal && (
              <div style={{ fontSize: 10, color: '#556677', marginTop: 6 }}>
                Digital signal: <b style={{ color: '#00d4ff' }}>{sparks.digital_signal.toUpperCase()}</b>
                {sparks.digital_ratio && ` (${sparks.digital_ratio.toFixed(2)}×)`}
              </div>
            )}
            {sparks.gamma_magnet && (
              <div style={{ fontSize: 10, color: '#556677', marginTop: 4 }}>
                Gamma magnet: <b style={{ color: '#f59e0b' }}>${sparks.gamma_magnet.strike}</b>
              </div>
            )}
            {velocityEvent?.detail && (
              <div style={{ fontSize: 10, color: '#7c8ca3', marginTop: 8, lineHeight: 1.55 }}>
                {velocityEvent.detail}
              </div>
            )}
          </>
        )}
      </div>

      {/* Spark event history */}
      {node.sparkHistory?.length > 0 && (
        <div>
          <div style={{ fontSize: 9, color: '#334455', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 8 }}>
            Session Event Log
          </div>
          {node.sparkHistory.map((ev, i) => (
            <div key={i} style={{
              fontSize: 10, padding: '7px 10px', marginBottom: 5,
              background: 'rgba(0,255,204,0.04)',
              borderLeft: '2px solid rgba(0,255,204,0.3)',
              borderRadius: '0 4px 4px 0', color: '#8899aa',
            }}>
              {ev}
            </div>
          ))}
        </div>
      )}

      {/* CIK link */}
      {detail?.cik && (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          <a
            href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${detail.cik}&type=8-K&dateb=&owner=include&count=10`}
            target="_blank" rel="noreferrer"
            style={{ fontSize: 10, color: '#334455', textDecoration: 'none', letterSpacing: 1 }}
            onMouseOver={e => e.target.style.color = '#00d4ff'}
            onMouseOut={e => e.target.style.color = '#334455'}
          >
            ↗ EDGAR FILINGS (CIK {detail.cik})
          </a>
        </div>
      )}

      {sympathyLeadTicker && (
        <div style={{ marginTop: 16, padding: '12px 13px', borderRadius: 16, background: 'rgba(215,180,106,0.06)', border: '1px solid rgba(215,180,106,0.14)' }}>
          <div style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-gold)', marginBottom: 8 }}>
            sympathy lead
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <div>
              <button
                type="button"
                onClick={() => jump(sympathyLeadTicker)}
                title={`Jump to ${sympathyLeadTicker}`}
                style={{
                  color: 'var(--hud-gold)',
                  fontSize: 15,
                  fontWeight: 700,
                  fontFamily: HUD_FONTS.display,
                  background: 'transparent',
                  border: 'none',
                  padding: 0,
                  margin: 0,
                  cursor: onJumpTo && sympathyLeadTicker !== node?.id ? 'pointer' : 'default',
                  textDecoration: onJumpTo ? 'underline dotted rgba(215,180,106,0.5)' : 'none',
                  textUnderlineOffset: 3,
                  letterSpacing: '0.04em',
                }}
              >
                {sympathyLeadTicker}
                {onJumpTo && sympathyLeadTicker !== node?.id && (
                  <span style={{ fontSize: 11, marginLeft: 6, color: 'rgba(215,180,106,0.65)' }}>↗</span>
                )}
              </button>
              <div style={{ fontSize: 10, color: 'var(--hud-muted)', marginTop: 4, letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: HUD_FONTS.mono }}>
                {liveSympathyLead?.label || `SYMPATHY: ${formatSectorLabel(sympathyLeadSector)}`}
              </div>
            </div>
            <div style={{
              padding: '5px 8px',
              borderRadius: 999,
              background: sympathyLeadRole === 'leader' ? 'rgba(95,208,170,0.1)' : 'rgba(114,229,255,0.08)',
              border: sympathyLeadRole === 'leader' ? '1px solid rgba(95,208,170,0.22)' : '1px solid rgba(114,229,255,0.18)',
              color: sympathyLeadRole === 'leader' ? 'var(--hud-success)' : 'var(--hud-cyan)',
              fontSize: 8,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              fontFamily: HUD_FONTS.mono,
              whiteSpace: 'nowrap',
            }}>
              {sympathyLeadRole === 'leader' ? 'lead ticker' : 'follow-through'}
            </div>
          </div>
          <div style={{ marginTop: 10, fontSize: 10, color: 'var(--hud-muted)', lineHeight: 1.65 }}>
            {sympathyLeadSummary}
          </div>
        </div>
      )}

      {/* ── Sympathy peer rail: click to hop ── */}
      {Array.isArray(sympathyPeers) && sympathyPeers.length > 0 && (
        <div style={{ marginTop: 14, padding: '12px 13px', borderRadius: 16, background: 'rgba(114,229,255,0.04)', border: '1px solid rgba(114,229,255,0.12)' }}>
          <div style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-cyan)', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            <span>sympathy peers</span>
            <span style={{ color: 'var(--hud-muted)', fontWeight: 400 }}>
              {sympathyPeers.length} linked
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {sympathyPeers.slice(0, 18).map(peer => (
              <button
                key={peer.id || peer.ticker || peer}
                type="button"
                onClick={() => jump(peer.id || peer.ticker || peer)}
                title={`Jump to ${peer.id || peer.ticker || peer}`}
                style={{
                  fontFamily: HUD_FONTS.mono,
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  padding: '4px 9px',
                  borderRadius: 999,
                  cursor: onJumpTo ? 'pointer' : 'default',
                  color: 'var(--hud-cyan)',
                  background: 'rgba(114,229,255,0.08)',
                  border: '1px solid rgba(114,229,255,0.22)',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'rgba(114,229,255,0.18)'
                  e.currentTarget.style.borderColor = 'rgba(114,229,255,0.48)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'rgba(114,229,255,0.08)'
                  e.currentTarget.style.borderColor = 'rgba(114,229,255,0.22)'
                }}
              >
                {peer.id || peer.ticker || peer}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── AI Intelligence Module ── */}
      <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 10, flexWrap: 'wrap' }}>
          <div style={{ ...monoLabel, fontSize: 9, color: 'var(--hud-muted-strong)' }}>
            AI intelligence
          </div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              padding: '5px 10px',
              borderRadius: 999,
              background: modelTone.bg,
              border: `1px solid ${modelTone.border}`,
              color: modelTone.color,
              fontSize: 8,
              letterSpacing: 1,
              fontFamily: HUD_FONTS.mono,
              textTransform: 'uppercase',
            }}>
              {modelLabel}
            </span>
            <span style={{ padding: '5px 10px', borderRadius: 999, background: sourceTone.bg, border: `1px solid ${sourceTone.border}`, color: sourceTone.accent, fontFamily: HUD_FONTS.mono, fontSize: 8, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase' }}>
              {sourceTone.label}
            </span>
          </div>
        </div>

        {aiLoading && <NeuralScanBar />}

        {!aiLoading && aiData && !aiData.pending && (
          <div style={{ animation: 'aiFadeIn 0.3s ease' }}>
            {/* Catalyst type + confidence */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              {aiData.catalyst_type && (
                <span style={{
                  fontSize: 9, fontWeight: 700, letterSpacing: 1, padding: '2px 7px',
                  borderRadius: 3,
                  background: `${CATALYST_COLORS[aiData.catalyst_type] || CATALYST_COLORS.UNKNOWN}18`,
                  border: `1px solid ${CATALYST_COLORS[aiData.catalyst_type] || CATALYST_COLORS.UNKNOWN}44`,
                  color: CATALYST_COLORS[aiData.catalyst_type] || CATALYST_COLORS.UNKNOWN,
                  textTransform: 'uppercase',
                }}>
                  {aiData.catalyst_type.replace(/_/g, ' ')}
                </span>
              )}
              {aiData.confidence != null && (
                <span style={{ fontSize: 9, color: '#445566', letterSpacing: 1 }}>
                  {Math.round(aiData.confidence * 100)}% conf
                </span>
              )}
              {aiData.filing_type && (
                <span style={{ fontSize: 9, color: '#2a3a4a', letterSpacing: 1, marginLeft: 'auto' }}>
                  {aiData.filing_type}
                  {aiData.filing_date ? ` · ${aiData.filing_date}` : ''}
                </span>
              )}
            </div>

            {/* Summary text */}
            <div style={{
              fontSize: 12, color: 'var(--hud-text)', lineHeight: 1.7,
              background: sourceTone.bg,
              border: `1px solid ${sourceTone.border}`,
              borderRadius: 16, padding: '12px 13px',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.03)',
            }}>
              {aiData.summary}
            </div>

            {sympathyHistory.length > 0 && (
              <div style={{ marginTop: 12, padding: '12px 13px', borderRadius: 16, background: 'rgba(81,242,198,0.05)', border: '1px solid rgba(81,242,198,0.12)' }}>
                <div style={{ ...monoLabel, fontSize: 8, color: 'rgba(81,242,198,0.86)', marginBottom: 8 }}>
                  sympathy trail
                </div>
                <div style={{ display: 'grid', gap: 8 }}>
                  {sympathyHistory.slice(0, 3).map((item, index) => (
                    <div key={`${item.date || 'undated'}-${index}`} style={{ fontSize: 10, color: 'var(--hud-muted)', lineHeight: 1.6 }}>
                      <div style={{ color: 'var(--hud-text)', fontWeight: 700 }}>
                        {item.relation === 'trigger' ? 'Primary sympathy trigger' : `Triggered by ${item.trigger_ticker || 'sector leader'}`}
                      </div>
                      <div>
                        {item.date || 'undated'}{item.sector ? ` · ${item.sector}` : ''}
                        {item.move_pct_t1day != null ? ` · T+1 ${item.move_pct_t1day > 0 ? '+' : ''}${Number(item.move_pct_t1day).toFixed(2)}%` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {memoryContext.length > 0 && (
              <div style={{ marginTop: 12, padding: '12px 13px', borderRadius: 16, background: 'rgba(114,229,255,0.04)', border: '1px solid rgba(114,229,255,0.12)' }}>
                <div style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-cyan)', marginBottom: 8 }}>
                  memory context
                </div>
                <div style={{ display: 'grid', gap: 8 }}>
                  {memoryContext.slice(0, 2).map((snippet, index) => (
                    <div key={index} style={{ fontSize: 10, color: 'var(--hud-muted)', lineHeight: 1.6 }}>
                      {snippet.split('\n')[0]}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!aiLoading && aiData?.pending && (
          <div style={{ fontSize: 11, color: 'var(--hud-muted)', fontStyle: 'italic', padding: '10px 0', letterSpacing: '0.02em' }}>
            Analysis pending - endpoint offline
          </div>
        )}
      </div>
    </div>
  )
}
