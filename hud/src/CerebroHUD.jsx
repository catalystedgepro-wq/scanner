import React, { Suspense, lazy, useState, useEffect, useRef, useCallback, useMemo } from 'react'
if (typeof window !== 'undefined') window.__HUD_BUILD = '20260413v9_gold_unified'
import { motion } from 'framer-motion'
import * as THREE from 'three'
import { Brain, Gauge, Orbit, Radar, Target } from 'lucide-react'
import ControlPanel from './ControlPanel.jsx'
import { HUD_FONTS, glassPanel, monoLabel, goldDivider } from './theme.js'
import { activeVelocityEvents, formatEventAge, liveEventsPerMinute, normalizeVelocityEvent, upsertVelocityEvent } from './velocityEvents.js'
import { CognitiveTopology } from '@/components/ui/cognitive-topology'

const NodeInspector = lazy(() => import('./NodeInspector.jsx'))
const VelocityDeck = lazy(() => import('./VelocityDeck.jsx'))

const API_BASE = ''   // relative — Nginx proxies /api/ → FastAPI port 8000
const WS_PROTO = window.location.protocol === 'https:' ? 'wss' : 'ws'
const WS_URL   = `${WS_PROTO}://${window.location.host}/ws/live`
const SCANNER_HOME_URL = 'https://catalystedgescanner.com'
const SCANNER_RETURN_STORAGE_KEY = 'cerebro-scanner-return-url'
const TARGET_LOCK_IDLE = {
  phase: 'idle',
  ticker: '',
  source: 'direct',
  rank: '',
  score: '',
  form: '',
  reason: '',
  channel: '',
  scannerOnly: false,
}
const LOCK_SEQUENCE_STEPS = ['acquiring', 'settling', 'locked']
const CAMERA_FOCUS_FRAME = {
  desktop: { fullWidthScale: 1, offsetScale: 0 },
  compact: { fullWidthScale: 1, offsetScale: 0 },
}
const INTERACTION_ASSIST = {
  hoverFreezeMs: 420,
  clickFreezeMs: 1600,
  handoffFreezeMs: 1800,
  hoverMagnetismMs: 220,
  backgroundDebounceMs: 220,
  hitTargetScale: 2.7,
  hitTargetMin: 7.8,
  denseHitTargetMin: 10.6,
  directMagnetPx: {
    cinematic: 18,
    balanced: 24,
    dense: 32,
  },
  sceneSafeInsets: {
    left: 128,
    right: 144,
    top: 112,
    bottom: 144,
  },
}
const BLOOM_PROFILE = {
  threshold: 0.72,
  deepBlueThreshold: 0.8,
  baseStrength: 0.34,
  deepBlueStrength: 0.22,
  phaseBoost: { acquiring: 0.12, settling: 0.18, locked: 0.24, idle: 0.02 },
  impulseBoost: 0.42,
  radius: 0.64,
  deepBlueRadius: 0.42,
}
const FIELD_DAMPING = {
  alphaDecay: 0.048,
  velocityDecay: 0.62,
  clockStep: { normal: 0.0041, deepBlue: 0.0015 },
  sceneRotation: { normal: 0.00013, deepBlue: 0.00004 },
  heartbeat: {
    normal: { base: 0.014, range: 0.01, speed: 1.08 },
    deep: { base: 0.005, range: 0.0035, speed: 0.48 },
  },
  link: {
    baseOpacity: 0.1,
    baseColor: 'rgba(196, 228, 255, 0.055)',
    sparkTouchColor: 'rgba(220, 241, 255, 0.1)',
    sparkPairColor: 'rgba(234, 244, 255, 0.14)',
    sympathyPositiveBase: '95, 208, 170',
    sympathyNegativeBase: '255, 122, 144',
    sympathyActivation: 0.18,
    sympathyMinAlpha: 0.06,
    sympathyMaxAlpha: 0.16,
    sympathyBaseWidth: 0.32,
    sympathyRangeWidth: 0.32,
    sparkTouchWidth: 0.3,
    sparkPairWidth: 0.48,
    selectionOpacity: {
      acquiring: 0.16,
      settling: 0.2,
      locked: 0.24,
      idle: 0.1,
    },
    selectionWidth: {
      acquiring: 0.76,
      settling: 1.02,
      locked: 1.34,
      idle: 0.72,
    },
  },
  particles: {
    acquiring: { count: 1, width: 1.4, speed: 0.0014 },
    settling: { count: 1, width: 1.7, speed: 0.0011 },
    locked: { count: 2, width: 1.8, speed: 0.00095 },
    idle: { count: 0, width: 0, speed: 0 },
  },
  peerOrbit: { normal: 0.28, deepBlue: 0.09, lift: 6 },
}
const COGNITIVE_STORM_CONFIG = {
  armCount: 5,
  armPoints: 96,
  particleCount: 460,
  baseRadius: 74,
}
const TELEMETRY_ACCENTS = {
  cyan: '#72e5ff',
  gold: '#f7c76f',
  green: '#5fd0aa',
  rose: '#ff7a90',
  violet: '#b08bff',
}
const HUD_RENDER_PROFILES = {
  cinematic: {
    name: 'cinematic',
    pixelRatio: 1.2,
    bloomEnabled: true,
    bloomStrengthScale: 1,
    visibleNodeBudget: Number.POSITIVE_INFINITY,
    starCount: 1800,
    nodeSegments: 16,
    shellSegments: 16,
    ringSegments: 48,
    richNodeBudget: Number.POSITIVE_INFINITY,
    animateDormantNodes: true,
    linkResolution: 8,
    sympathyParticleScale: 1,
    orbitPeers: 5,
    gravityRingCount: 8,
    peerRingCount: 5,
    gammaSegments: 32,
    starOpacity: 0.6,
    structuralAdjacencyDepth: 2,
    force: { alphaDecay: 0.048, velocityDecay: 0.62 },
  },
  balanced: {
    name: 'balanced',
    pixelRatio: 1.05,
    bloomEnabled: true,
    bloomStrengthScale: 0.72,
    visibleNodeBudget: 2400,
    starCount: 800,
    nodeSegments: 10,
    shellSegments: 10,
    ringSegments: 32,
    richNodeBudget: 160,
    animateDormantNodes: false,
    linkResolution: 6,
    sympathyParticleScale: 0.72,
    orbitPeers: 4,
    gravityRingCount: 6,
    peerRingCount: 4,
    gammaSegments: 22,
    starOpacity: 0.46,
    structuralAdjacencyDepth: 1,
    force: { alphaDecay: 0.058, velocityDecay: 0.66 },
  },
  dense: {
    name: 'dense',
    pixelRatio: 1,
    bloomEnabled: false,
    bloomStrengthScale: 0.45,
    visibleNodeBudget: 1320,
    starCount: 320,
    nodeSegments: 8,
    shellSegments: 8,
    ringSegments: 24,
    richNodeBudget: 22,
    animateDormantNodes: false,
    linkResolution: 3,
    sympathyParticleScale: 0.25,
    orbitPeers: 3,
    gravityRingCount: 4,
    peerRingCount: 3,
    gammaSegments: 16,
    starOpacity: 0.34,
    structuralAdjacencyDepth: 1,
    force: { alphaDecay: 0.072, velocityDecay: 0.72 },
  },
}
const DENSE_SHELL_LAYOUT = {
  shellRadiusX: 418,
  shellRadiusY: 252,
  shellRadiusZ: 336,
  shellDrift: 54,
  sectorSpread: 42,
  focusDepth: 112,
  focusLift: 20,
  focusScale: 0.82,
  hoverScale: 0.94,
  lateralBias: -24,
}
const MARKET_MEMBRANE_CONFIG = {
  outer: { x: 468, y: 286, z: 378 },
  inner: { x: 328, y: 196, z: 264 },
  shellPoints: 2600,
  corePoints: 1600,
  pulsePoints: 320,
  meridianCount: 5,
  latitudeCount: 4,
}
const TARGET_LOCK_PHASE_STYLE = {
  acquiring: {
    label: 'acquiring',
    modeLabel: 'uplink aperture',
    cueLabel: 'packet intercept',
    tone: 'var(--hud-cyan)',
    border: 'rgba(114,229,255,0.24)',
    glow: 'rgba(114,229,255,0.16)',
    rail: 'linear-gradient(90deg, rgba(114,229,255,0.15) 0%, rgba(114,229,255,0.72) 100%)',
    progress: 0.34,
    linkColor: 'rgba(114,229,255,0.22)',
    focusTone: 'scan',
    marker: {
      spin: 0.0024,
      scaleBase: 0.95,
      scaleRange: 0.035,
      scaleSpeed: 2.1,
      anchorBase: 0.62,
      anchorRange: 0.05,
      anchorSpeed: 1.9,
      sweepOpacity: 0.34,
      sweepSpeed: 0.0074,
      sweepScaleBase: 1.05,
      sweepScaleRange: 0.035,
      haloBase: 0.07,
      haloRange: 0.024,
      haloSpeed: 1.7,
      beamBase: 0.16,
      beamRange: 0.028,
      beamSpeed: 2.0,
      beamScaleBase: 1.16,
      beamScaleRange: 0.05,
      reticleOpacity: 0.22,
      reticleSpeed: 0.007,
      apertureOffset: 1.18,
      apertureDrift: 0.07,
      apertureSpeed: 2.0,
      apertureOpacity: 0.26,
    },
    audio: {
      wave: 'triangle',
      tones: [188, 208, 182],
      sweep: [208, 214, 176],
      duration: 0.08,
      spacing: 0.055,
      gain: 0.013,
      filter: 1420,
    },
  },
  settling: {
    label: 'settling',
    modeLabel: 'inertial clamp',
    cueLabel: 'vector damping',
    tone: 'var(--hud-gold)',
    border: 'rgba(231,183,108,0.26)',
    glow: 'rgba(231,183,108,0.14)',
    rail: 'linear-gradient(90deg, rgba(114,229,255,0.14) 0%, rgba(231,183,108,0.88) 100%)',
    progress: 0.68,
    linkColor: 'rgba(231,183,108,0.28)',
    focusTone: 'settle',
    marker: {
      spin: 0.0012,
      scaleBase: 0.992,
      scaleRange: 0.012,
      scaleSpeed: 1.35,
      anchorBase: 0.76,
      anchorRange: 0.02,
      anchorSpeed: 1.2,
      sweepOpacity: 0.22,
      sweepSpeed: 0.0035,
      sweepScaleBase: 1.02,
      sweepScaleRange: 0.012,
      haloBase: 0.05,
      haloRange: 0.01,
      haloSpeed: 1.1,
      beamBase: 0.13,
      beamRange: 0.012,
      beamSpeed: 1.2,
      beamScaleBase: 1.02,
      beamScaleRange: 0.025,
      reticleOpacity: 0.16,
      reticleSpeed: 0.0038,
      apertureOffset: 1.04,
      apertureDrift: 0.025,
      apertureSpeed: 1.0,
      apertureOpacity: 0.2,
    },
    audio: {
      wave: 'triangle',
      tones: [156, 148],
      sweep: [138, 128],
      duration: 0.11,
      spacing: 0.08,
      gain: 0.012,
      filter: 1180,
    },
  },
  locked: {
    label: 'engaged',
    modeLabel: 'mechanical seal',
    cueLabel: 'console ingest complete',
    tone: 'var(--hud-success)',
    border: 'rgba(95,208,170,0.28)',
    glow: 'rgba(95,208,170,0.16)',
    rail: 'linear-gradient(90deg, rgba(231,183,108,0.24) 0%, rgba(95,208,170,0.92) 100%)',
    progress: 1,
    linkColor: 'rgba(95,208,170,0.34)',
    focusTone: 'lock',
    marker: {
      spin: 0.00055,
      scaleBase: 1.01,
      scaleRange: 0.006,
      scaleSpeed: 0.82,
      anchorBase: 0.88,
      anchorRange: 0.01,
      anchorSpeed: 0.8,
      sweepOpacity: 0.12,
      sweepSpeed: 0.0016,
      sweepScaleBase: 1,
      sweepScaleRange: 0.006,
      haloBase: 0.04,
      haloRange: 0.008,
      haloSpeed: 0.82,
      beamBase: 0.17,
      beamRange: 0.01,
      beamSpeed: 0.8,
      beamScaleBase: 0.96,
      beamScaleRange: 0.014,
      reticleOpacity: 0.11,
      reticleSpeed: 0.0019,
      apertureOffset: 0.94,
      apertureDrift: 0.012,
      apertureSpeed: 0.65,
      apertureOpacity: 0.18,
    },
    audio: {
      wave: 'sine',
      tones: [196, 294, 392],
      sweep: [220, 330, 440],
      duration: 0.14,
      spacing: 0.07,
      gain: 0.018,
      filter: 1820,
    },
  },
  idle: {
    label: 'idle',
    modeLabel: 'standby',
    cueLabel: 'command rail armed',
    tone: 'var(--hud-muted)',
    border: 'rgba(255,255,255,0.08)',
    glow: 'rgba(255,255,255,0.03)',
    rail: 'linear-gradient(90deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.18) 100%)',
    progress: 0,
    linkColor: 'rgba(255,255,255,0.08)',
    focusTone: 'lock',
    marker: {
      spin: 0.001,
      scaleBase: 1,
      scaleRange: 0,
      scaleSpeed: 1,
      anchorBase: 0.48,
      anchorRange: 0.02,
      anchorSpeed: 1.2,
      sweepOpacity: 0.12,
      sweepSpeed: 0.002,
      sweepScaleBase: 1,
      sweepScaleRange: 0,
      haloBase: 0.03,
      haloRange: 0.01,
      haloSpeed: 1,
      beamBase: 0.08,
      beamRange: 0.01,
      beamSpeed: 1,
      beamScaleBase: 1,
      beamScaleRange: 0,
      reticleOpacity: 0.1,
      reticleSpeed: 0.003,
      apertureOffset: 1,
      apertureDrift: 0,
      apertureSpeed: 1,
      apertureOpacity: 0.12,
    },
    audio: null,
  },
}
const FOCUS_STATUS_STYLE = {
  scan: {
    border: '1px solid rgba(114,229,255,0.18)',
    background: 'rgba(114,229,255,0.06)',
    color: 'var(--hud-cyan)',
  },
  settle: {
    border: '1px solid rgba(231,183,108,0.2)',
    background: 'rgba(231,183,108,0.08)',
    color: 'var(--hud-gold)',
  },
  lock: {
    border: '1px solid rgba(95,208,170,0.2)',
    background: 'rgba(95,208,170,0.08)',
    color: 'var(--hud-success)',
  },
  error: {
    border: '1px solid rgba(255,122,144,0.22)',
    background: 'rgba(255,122,144,0.08)',
    color: '#ffb2bf',
  },
}

// ── Weather tether helpers ────────────────────────────────────────────────────
function makeJaggedLine(start, end, segments = 10, jitter = 12) {
  const pts = []
  for (let i = 0; i <= segments; i++) {
    const t  = i / segments
    const ox = i > 0 && i < segments ? (Math.random() - 0.5) * jitter : 0
    const oy = i > 0 && i < segments ? (Math.random() - 0.5) * jitter : 0
    pts.push(new THREE.Vector3(
      start.x + (end.x - start.x) * t + ox,
      start.y + (end.y - start.y) * t + oy,
      (start.z || 0) + ((end.z || 0) - (start.z || 0)) * t,
    ))
  }
  return pts
}

function makeArcedLine(start, end, lift = 65, segments = 24) {
  const a = new THREE.Vector3(start.x, start.y, start.z || 0)
  const b = new THREE.Vector3(end.x, end.y, end.z || 0)
  const mid = a.clone().lerp(b, 0.5)
  mid.y += lift
  const curve = new THREE.CatmullRomCurve3([a, mid, b])
  return curve.getPoints(segments)
}

function buildWeatherStroke(points, color, options = {}) {
  const curve = new THREE.CatmullRomCurve3(points)
  const group = new THREE.Group()
  const pointCount = options.pointCount || 36
  const linePoints = curve.getPoints(pointCount)

  const shell = new THREE.Mesh(
    new THREE.TubeGeometry(curve, options.tubularSegments || 52, options.radius || 0.85, 10, false),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: options.shellOpacity ?? 0.2,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  )
  shell.userData.weatherGlow = {
    baseOpacity: options.shellOpacity ?? 0.2,
    range: options.shellRange ?? 0.08,
    speed: options.speed ?? 4.2,
    phase: options.phase ?? Math.random() * Math.PI * 2,
  }

  const core = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(linePoints),
    new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: options.coreOpacity ?? 0.8,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  )
  core.userData.weatherGlow = {
    baseOpacity: options.coreOpacity ?? 0.8,
    range: options.coreRange ?? 0.1,
    speed: (options.speed ?? 4.2) * 1.25,
    phase: (options.phase ?? 0) + 0.8,
  }

  const flare = new THREE.Mesh(
    new THREE.SphereGeometry(options.flareRadius ?? 2.4, 14, 14),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: options.flareOpacity ?? 0.32,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  )
  flare.position.copy(points[points.length - 1])
  flare.userData.weatherGlow = {
    baseOpacity: options.flareOpacity ?? 0.32,
    range: options.flareRange ?? 0.12,
    speed: (options.speed ?? 4.2) * 1.4,
    phase: (options.phase ?? 0) + 1.3,
  }

  group.add(shell, core, flare)
  return group
}

const SECTOR_COLORS = {
  tech:        '#d7f3ff', semis:       '#dbe5ff', biotech:     '#d8fff3',
  financials:  '#edf6ff', energy:      '#f5f8ff', materials:   '#edf8ff',
  industrials: '#deebff', consumer:    '#f3fbff', staples:     '#e4fcff',
  comms:       '#efe6ff', utilities:   '#e6ecff', real_estate: '#f3efff',
  unknown:     '#7e95ae',
}
const HUD_FIELD_BASE = '#07111a'
const HUD_NODE_BASE = '#dff8ff'
const HUD_NODE_BRIGHT = '#f6fdff'
const HUD_NODE_BULL = '#d6fff0'
const HUD_NODE_BEAR = '#efe5ff'
const POLARITY_FIELD_COLORS = {
  bullish: '#66f5cf',
  bearish: '#ff728f',
  neutral: '#72e5ff',
  targeted: '#e7b76c',
}
const FORCE_GRAPH_NODE_COLORS = {
  bull: '#10b981',
  bear: '#f43f5e',
  neutral: '#64748b',
}
// Saturated sector colors for 3D node rendering (base hue per sector)
const SECTOR_NODE_COLORS = {
  tech:        '#38bdf8', // sky blue
  semis:       '#818cf8', // indigo
  biotech:     '#34d399', // emerald
  financials:  '#fbbf24', // amber
  energy:      '#fb923c', // orange
  materials:   '#a3e635', // lime
  industrials: '#60a5fa', // blue
  consumer:    '#f472b6', // pink
  staples:     '#2dd4bf', // teal
  comms:       '#c084fc', // purple
  utilities:   '#a78bfa', // violet
  real_estate: '#f59e0b', // yellow
  unknown:     '#94a3b8', // slate
  other:       '#94a3b8',
}
const FORCE_GRAPH_SECTOR_COLOR_CHANNELS = {
  technology: '56, 189, 248',
  healthcare: '167, 139, 250',
  energy: '250, 204, 21',
  financials: '52, 211, 153',
  'consumer cyclical': '244, 114, 182',
}

function sectorColor(s) { return SECTOR_COLORS[s] || SECTOR_COLORS.unknown }
function brightnessToSize(b) { return Math.max(2.2, Math.min(11, b / 7.5)) }
function compactReason(text = '') {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  return normalized.length > 88 ? `${normalized.slice(0, 85)}…` : normalized
}

function summarizeMarketPulse(events = [], sympathyTotal = 0) {
  let positive = 0
  let negative = 0
  let hottest = null

  events.forEach(event => {
    const velocity = Number(event?.total_velocity || 0)
    if (velocity > 0) positive += velocity
    else negative += Math.abs(velocity)

    if (!hottest || Math.abs(velocity) > Math.abs(Number(hottest?.total_velocity || 0))) {
      hottest = event
    }
  })

  const total = positive + negative
  let bias = 'balanced'
  if (total < 0.8) bias = 'quiet'
  else if (positive > negative * 1.16) bias = 'bullish'
  else if (negative > positive * 1.16) bias = 'bearish'

  return {
    bias,
    positive,
    negative,
    total,
    sympathyTotal,
    intensity: Math.max(0.16, Math.min(1, (total + sympathyTotal * 0.5) / 26)),
    hottestTicker: hottest?.ticker || hottest?.id || '',
    hottestHeadline: hottest?.headline || hottest?.detail || '',
    hottestVelocity: Number(hottest?.total_velocity || 0),
  }
}

function formatSectorLabel(sector = '') {
  const normalized = String(sector || '')
    .replace(/_/g, ' ')
    .trim()
  if (!normalized) return 'GENERAL'
  return normalized.toUpperCase()
}

function velocityValue(node) {
  return Number(node?.velocityEvent?.total_velocity || 0)
}

function normalizeForceSector(sector = '') {
  const normalized = String(sector || '').trim().toLowerCase()
  switch (normalized) {
    case 'tech':
    case 'semis':
    case 'comms':
      return 'technology'
    case 'biotech':
    case 'healthcare':
      return 'healthcare'
    case 'energy':
      return 'energy'
    case 'financials':
    case 'real_estate':
      return 'financials'
    case 'consumer':
    case 'staples':
      return 'consumer cyclical'
    default:
      return normalized
  }
}

function deriveNodePosture(node) {
  const explicit = String(node?.posture || node?.market_posture || '').trim().toLowerCase()
  if (explicit.includes('bull')) return 'bull'
  if (explicit.includes('bear')) return 'bear'

  const velocity = Number(node?.velocityEvent?.total_velocity || node?.velocity || 0)
  if (velocity > 0.15) return 'bull'
  if (velocity < -0.15) return 'bear'

  const gravity = Number(node?.gravity)
  if (Number.isFinite(gravity) && gravity < 0) return 'bear'
  return 'neutral'
}

function getNodeColor(node) {
  // Primary hue = sector, posture modulates brightness/saturation
  const sector = String(node?.sector || 'unknown').toLowerCase()
  const sectorBase = SECTOR_NODE_COLORS[sector] || SECTOR_NODE_COLORS.unknown
  const posture = node?.posture || 'neutral'
  const gravity = Number(node?.gravity || 0)

  // For bull/bear, blend sector color toward posture accent
  if (posture === 'bull' || gravity > 0) {
    return blendHudColor(sectorBase, '#d6fff0', 0.2)
  }
  if (posture === 'bear' || gravity < 0) {
    return blendHudColor(sectorBase, '#efe5ff', 0.15)
  }
  return sectorBase
}

function getLinkColor(link, sourceNode, targetNode, alpha = 0.4) {
  const sectorColors = {
    Technology: '56, 189, 248',
    Healthcare: '167, 139, 250',
    Energy: '250, 204, 21',
    Financials: '52, 211, 153',
    'Consumer Cyclical': '244, 114, 182',
  }
  const sectorAliases = {
    tech: 'Technology',
    technology: 'Technology',
    semis: 'Technology',
    biotech: 'Healthcare',
    healthcare: 'Healthcare',
    energy: 'Energy',
    financials: 'Financials',
    consumer: 'Consumer Cyclical',
    'consumer cyclical': 'Consumer Cyclical',
  }
  const rawSector = String(
    link?.sector
      || link?.sympathySector
      || sourceNode?.sector
      || targetNode?.sector
      || (typeof link?.source === 'object' ? link?.source?.sector : '')
      || (typeof link?.target === 'object' ? link?.target?.sector : '')
      || '',
  ).trim()
  const sectorKey = sectorColors[rawSector]
    ? rawSector
    : sectorAliases[rawSector.toLowerCase()] || ''
  return sectorKey
    ? `rgba(${sectorColors[sectorKey]}, ${alpha})`
    : 'rgba(255, 255, 255, 0.05)'
}

function blendHudColor(from, to, mix = 0.5) {
  const a = new THREE.Color(from || SECTOR_COLORS.unknown)
  const b = new THREE.Color(to || HUD_FIELD_BASE)
  return `#${a.lerp(b, Math.max(0, Math.min(1, mix))).getHexString()}`
}

function polarityAccentFromVelocity(value = 0) {
  if (value > 0.15) return POLARITY_FIELD_COLORS.bullish
  if (value < -0.15) return POLARITY_FIELD_COLORS.bearish
  return POLARITY_FIELD_COLORS.neutral
}

function dormantNodeColor(node) {
  const gravity = Math.max(0, Math.min(1, Math.abs(Number(node?.gravity || 0)) / 60))
  const postureColor = new THREE.Color(getNodeColor(node))
  const color = postureColor
    .clone()
    .lerp(new THREE.Color(HUD_NODE_BRIGHT), 0.12 + gravity * 0.12)
  return `#${color.getHexString()}`
}

function pressureNodeColor(node) {
  const postureColor = getNodeColor(node)
  if (node?.hasSpark) return blendHudColor(postureColor, '#ffffff', 0.18)
  return postureColor
}

function clusterShapeForNode(node) {
  if (node?.scanner_only) return 'octa'
  switch (node?.sector) {
    case 'tech': return 'box'
    case 'semis': return 'octa'
    case 'biotech': return 'sphere'
    case 'financials': return 'dodeca'
    case 'energy': return 'tetra'
    case 'materials': return 'box'
    case 'industrials': return 'icosa'
    case 'consumer': return 'sphere'
    case 'staples': return 'capsule'
    case 'comms': return 'octa'
    case 'utilities': return 'dodeca'
    case 'real_estate': return 'box'
    default: return 'sphere'
  }
}

function makeNodeGeometry(shape, radius, segments) {
  switch (shape) {
    case 'box':
      return new THREE.BoxGeometry(radius * 1.62, radius * 1.62, radius * 1.62, 1, 1, 1)
    case 'octa':
      return new THREE.OctahedronGeometry(radius * 1.18, 0)
    case 'dodeca':
      return new THREE.DodecahedronGeometry(radius * 1.08, 0)
    case 'icosa':
      return new THREE.IcosahedronGeometry(radius * 1.1, 0)
    case 'tetra':
      return new THREE.TetrahedronGeometry(radius * 1.28, 0)
    case 'capsule':
      return new THREE.CapsuleGeometry(Math.max(radius * 0.52, 0.85), radius * 1.26, 4, Math.max(4, segments))
    default:
      return new THREE.SphereGeometry(radius, segments, segments)
  }
}

// Velocity normalization: 95th-percentile of pairwise velocity sums.
// Severity thresholds: >=18 critical, >=10 elevated. Two elevated stocks
// sum to ~20; two critical sum to ~36. 40 ≈ 95th-pct upper bound.
const VELOCITY_UPPER_BOUND = 40

// F-5/A-11 fix: Use pre-computed sector correlation when available
// (Lo & MacKinlay 1990, Cont 2001). Falls back to velocity-sum proxy.
// sympathyMatrixRef is set from /api/sympathy fetch in the main component.
let _sympathyMatrix = null
function setSympathyMatrix(matrix) { _sympathyMatrix = matrix }

function sympathyStrengthBetween(sourceNode, targetNode) {
  // Try correlation-based strength first (A-11)
  if (_sympathyMatrix) {
    const sSector = sourceNode?.sector || ''
    const tSector = targetNode?.sector || ''
    if (sSector && tSector && _sympathyMatrix[sSector]?.[tSector] !== undefined) {
      const corr = Math.abs(_sympathyMatrix[sSector][tSector])
      // Blend: 70% correlation + 30% velocity (correlation dominates but velocity adds recency)
      const sourceVelocity = Math.abs(velocityValue(sourceNode))
      const targetVelocity = Math.abs(velocityValue(targetNode))
      const velComponent = Math.min(1, (sourceVelocity + targetVelocity) / VELOCITY_UPPER_BOUND)
      return Math.min(1, corr * 0.7 + velComponent * 0.3)
    }
  }
  // Fallback: velocity-sum proxy
  const sourceVelocity = Math.abs(velocityValue(sourceNode))
  const targetVelocity = Math.abs(velocityValue(targetNode))
  return Math.min(1, (sourceVelocity + targetVelocity) / VELOCITY_UPPER_BOUND)
}

// F-12 fix: Polarity now reflects whether sectors actually move together
function sympathyPolarityBetween(sourceNode, targetNode) {
  if (_sympathyMatrix) {
    const sSector = sourceNode?.sector || ''
    const tSector = targetNode?.sector || ''
    if (sSector && tSector && _sympathyMatrix[sSector]?.[tSector] !== undefined) {
      return _sympathyMatrix[sSector][tSector]  // positive = sympathetic, negative = divergent
    }
  }
  return velocityValue(sourceNode) + velocityValue(targetNode)
}

function sympathyColor(link) {
  const strength = Math.max(0, Math.min(1, Number(link?.sympathyStrength || 0)))
  const alpha = FIELD_DAMPING.link.sympathyMinAlpha + (FIELD_DAMPING.link.sympathyMaxAlpha - FIELD_DAMPING.link.sympathyMinAlpha) * strength
  return getLinkColor(link, null, null, Number(alpha.toFixed(3)))
}

function materialSupportsColor(material) {
  return Boolean(material?.color?.set)
}

function materialSupportsEmissive(material) {
  return Boolean(material?.emissive?.set)
}

function setMaterialColor(material, color) {
  if (!materialSupportsColor(material)) return
  material.color.set(color)
}

function setMaterialEmissive(material, color) {
  if (!materialSupportsEmissive(material)) return
  material.emissive.set(color)
}

function setMaterialEmissiveIntensity(material, value) {
  if (typeof material?.emissiveIntensity !== 'number') return
  material.emissiveIntensity = value
}

function makeHudBadgeSprite(lines, options = {}) {
  if (typeof document === 'undefined') return null
  const lineItems = (Array.isArray(lines) ? lines : [lines]).filter(Boolean)
  if (!lineItems.length) return null

  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  const accent = options.accent || '#72e5ff'
  const border = options.border || 'rgba(114,229,255,0.42)'
  const background = options.background || 'rgba(6,14,24,0.84)'
  const subColor = options.subColor || 'rgba(214,225,238,0.82)'
  const fontFamily = 'ui-monospace, SFMono-Regular, Menlo, monospace'
  const titleSize = 30
  const bodySize = 22
  const padX = 28
  const padY = 22
  const lineGap = 10

  const widths = lineItems.map((line, index) => {
    ctx.font = `${index === 0 ? 700 : 500} ${index === 0 ? titleSize : bodySize}px ${fontFamily}`
    return ctx.measureText(line).width
  })

  const width = Math.ceil(Math.max(...widths) + padX * 2)
  const height = Math.ceil(
    padY * 2 +
    lineItems.reduce((total, _, index) => total + (index === 0 ? titleSize : bodySize), 0) +
    lineGap * Math.max(0, lineItems.length - 1),
  )

  canvas.width = width * 2
  canvas.height = height * 2
  ctx.scale(2, 2)

  const radius = 18
  ctx.fillStyle = background
  ctx.strokeStyle = border
  ctx.lineWidth = 1.4
  ctx.beginPath()
  ctx.moveTo(radius, 0)
  ctx.lineTo(width - radius, 0)
  ctx.quadraticCurveTo(width, 0, width, radius)
  ctx.lineTo(width, height - radius)
  ctx.quadraticCurveTo(width, height, width - radius, height)
  ctx.lineTo(radius, height)
  ctx.quadraticCurveTo(0, height, 0, height - radius)
  ctx.lineTo(0, radius)
  ctx.quadraticCurveTo(0, 0, radius, 0)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()

  let y = padY + titleSize * 0.82
  lineItems.forEach((line, index) => {
    const isTitle = index === 0
    ctx.font = `${isTitle ? 700 : 500} ${isTitle ? titleSize : bodySize}px ${fontFamily}`
    ctx.fillStyle = isTitle ? accent : subColor
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(line, padX, y)
    y += (isTitle ? titleSize : bodySize) + lineGap
  })

  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    opacity: options.opacity ?? 1,
  })
  const sprite = new THREE.Sprite(material)
  const scale = options.scale ?? 0.055
  sprite.scale.set(width * scale, height * scale, 1)
  sprite.userData.baseScale = { x: sprite.scale.x, y: sprite.scale.y, z: 1 }
  sprite.renderOrder = 12
  return sprite
}

function makeJarvisApertureMaterial(color, options = {}) {
  const resolvedColor = new THREE.Color(color || '#72e5ff')
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uColor: { value: resolvedColor },
      uTime: { value: 0 },
      uOpacity: { value: options.opacity ?? 0.34 },
      uImpact: { value: 0 },
      uProgress: { value: options.progress ?? 0.6 },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv * 2.0 - 1.0;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec2 vUv;
      uniform vec3 uColor;
      uniform float uTime;
      uniform float uOpacity;
      uniform float uImpact;
      uniform float uProgress;

      float sdHex(vec2 p, float r) {
        p = abs(p);
        return max(dot(p, normalize(vec2(1.0, 1.7320508))), p.x) - r;
      }

      void main() {
        vec2 uv = vUv;
        float radial = length(uv);
        float angle = atan(uv.y, uv.x);
        float wobble = sin(uTime * 1.8 + radial * 9.0) * 0.008;
        float outerHex = abs(sdHex(uv, 0.80 + wobble));
        float innerHex = abs(sdHex(uv, 0.58 + wobble * 0.5));
        float outerRing = smoothstep(0.045, 0.0, outerHex - 0.015);
        float innerRing = smoothstep(0.035, 0.0, innerHex - 0.01);
        float radialRing = smoothstep(0.66, 0.61, radial) * (1.0 - smoothstep(0.80, 0.84, radial));
        float spokes = pow(max(0.0, cos(angle * 6.0)), 24.0) * smoothstep(0.86, 0.22, radial);
        float scan = smoothstep(0.78, 1.0, sin(angle * 6.0 + uTime * 2.2) * 0.5 + 0.5);
        float pulse = 0.72 + 0.28 * sin(uTime * 2.6 + radial * 10.0 + uImpact * 3.14);
        float glow = max(outerRing, radialRing * 0.85) + innerRing * 0.65 + spokes * 0.24;
        float alpha = glow * uOpacity * pulse * clamp(uProgress, 0.18, 1.0);
        alpha += scan * 0.08 * clamp(uProgress, 0.18, 1.0);
        alpha += uImpact * 0.14 * (1.0 - smoothstep(0.15, 0.92, radial));
        if (alpha < 0.018) discard;
        vec3 color = uColor * (1.0 + scan * 0.08 + uImpact * 0.12);
        gl_FragColor = vec4(color, alpha);
      }
    `,
  })
  material.userData.jarvisShader = true
  return material
}

const HUD_SECTOR_ALIASES = {
  tech: 'tech',
  technology: 'tech',
  semis: 'semis',
  semiconductor: 'semis',
  semiconductors: 'semis',
  biotech: 'biotech',
  healthcare: 'biotech',
  'health care': 'biotech',
  financials: 'financials',
  'financial services': 'financials',
  energy: 'energy',
  industrials: 'industrials',
  industrial: 'industrials',
  materials: 'materials',
  utilities: 'utilities',
  consumer: 'consumer',
  'consumer cyclical': 'consumer',
  'consumer discretionary': 'consumer',
  staples: 'staples',
  'consumer defensive': 'staples',
  comms: 'comms',
  communications: 'comms',
  'communication services': 'comms',
  'real estate': 'real_estate',
  real_estate: 'real_estate',
  other: 'other',
  unknown: 'unknown',
}

function normalizeHudSector(rawSector = '') {
  const cleaned = String(rawSector || '')
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return 'other'
  return HUD_SECTOR_ALIASES[cleaned] || cleaned.replace(/\s+/g, '_')
}

function resolveHudSector(node = {}) {
  const candidates = [
    node?.sector,
    node?.Sector,
    node?.gics?.s,
    node?.gics_sector,
    node?.industry,
  ]
    .map(value => String(value || '').trim())
    .filter(Boolean)

  if (!candidates.length) return 'other'

  const preferred = candidates.find(value => {
    const normalized = normalizeHudSector(value)
    return normalized !== 'other' && normalized !== 'unknown'
  })

  return normalizeHudSector(preferred || candidates[0] || 'other')
}

function processData(data = {}) {
  const rawNodes = Array.isArray(data?.nodes)
    ? data.nodes
    : Array.isArray(data?.tickers)
      ? data.tickers
      : Array.isArray(data)
        ? data
        : []
  const nodes = rawNodes.map(node => ({
    ...node,
    sector: resolveHudSector(node),
  }))
  return {
    nodes,
    links: Array.isArray(data?.links) ? data.links : [],
  }
}

function buildHudNodeFromUniverseRow(row) {
  const scannerOnly = Boolean(row?.scanner_only)
  const isRogue = Boolean(row?.is_rogue)
  const brightness = Number(row?.brightness || 0)
  const totalVelocity = Number(row?.velocity_event?.total_velocity || 0)
  const sparks = row?.sparks || null
  const sector = resolveHudSector(row)
  const posture = deriveNodePosture({
    posture: row?.posture || row?.market_posture || '',
    gravity: Number(row?.gravity || 0),
    velocityEvent: row?.velocity_event || null,
  })
  const liveColor = getNodeColor({
    posture,
    sector,
    gravity: Number(row?.gravity || 0),
    velocityEvent: row?.velocity_event || null,
  })
  const dormantColor = dormantNodeColor({
    posture,
    sector,
    gravity: Number(row?.gravity || 0),
    velocityEvent: row?.velocity_event || null,
  })
  const pressureColor = pressureNodeColor({
    posture,
    sector,
    gravity: Number(row?.gravity || 0),
    hasSpark: Math.abs(totalVelocity) > 0 || Boolean(sparks),
    velocityEvent: row?.velocity_event || null,
  })

  return {
    id:              row?.ticker,
    ticker:          row?.ticker,
    name:            row?.name || '',
    gravity:         Number(row?.gravity || 0),
    brightness,
    sector,
    cap_tier:        row?.cap_tier || '',
    etf_overlords:   (row?.etf_overlords || []).filter(e => typeof e === 'object' && e.etf).map(e => ({
      ...e,
      calculatedOpacity: Math.min(0.9, 0.2 + 0.7 * Math.sqrt((e.weight || 0) / 10)),
    })),
    is_rogue:        isRogue,
    scanner_only:    scannerOnly,
    scanner_sources: row?.scanner_sources || [],
    scanner_rank:    row?.scanner_rank ?? null,
    scanner_score:   row?.scanner_score ?? null,
    scanner_form:    row?.scanner_form || '',
    scanner_tags:    row?.scanner_tags || '',
    scanner_link:    row?.scanner_link || '',
    sector_source:   row?.sector_source || '',
    sector_inferred: Boolean(row?.sector_inferred),
    sector_evidence: row?.sector_evidence || '',
    posture,
    baseColor:       isRogue ? '#f6fdff' : liveColor,
    dormantColor,
    pressureColor,
    sparkTint:       Math.abs(totalVelocity) > 0.15 ? pressureColor : null,
    val:             brightnessToSize(brightness),
    color:           Math.abs(totalVelocity) > 0.15 ? pressureColor : dormantColor,
    emissiveInt:     isRogue ? 0.35 : Math.abs(totalVelocity) > 0.15 ? Math.max(Math.abs(totalVelocity) / 18, 0.16) : scannerOnly ? 0.08 : 0.02,
    sparks,
    velocityEvent:   row?.velocity_event || null,
    hasSpark:        Math.abs(totalVelocity) > 0 || Boolean(sparks),
    sparkHistory:    row?.sparkHistory || [],
    gammaSize:       Number(row?.gammaSize || 0),
  }
}

function scannerRankWeight(node) {
  const rank = Number(node?.scanner_rank)
  if (!Number.isFinite(rank) || rank <= 0) return 0
  return Math.max(0, 420 - rank * 18)
}

function nodePriorityScore(node, focus = {}) {
  if (!node) return -1
  const id = node.id || node.ticker || ''
  const isSelected = focus.selectedTicker && id === focus.selectedTicker
  const isTargetLock = focus.targetTicker && id === focus.targetTicker
  const isHovered = focus.hoverTicker && id === focus.hoverTicker
  const sparkBoost = node.hasSpark ? 900 : 0
  const scannerBoost = scannerRankWeight(node) + (Number(node?.scanner_score || 0) * 8)
  const brightnessBoost = Number(node?.brightness || 0) * 1.2
  const gravityBoost = Number(node?.gravity || 0) * 14
  const sectorBoost = focus.focusSector && node.sector === focus.focusSector ? 120 : 0
  const parityBoost = node.scanner_only ? 60 : 0
  return (
    (isSelected ? 5000 : 0)
    + (isTargetLock ? 4200 : 0)
    + (isHovered ? 900 : 0)
    + sparkBoost
    + scannerBoost
    + brightnessBoost
    + gravityBoost
    + sectorBoost
    + parityBoost
  )
}

function hashCode(value = '') {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

function fibonacciSpherePoint(index, total, radius) {
  const safeTotal = Math.max(1, total)
  const offset = 2 / safeTotal
  const increment = Math.PI * (3 - Math.sqrt(5))
  const y = ((index * offset) - 1) + (offset / 2)
  const distance = Math.sqrt(Math.max(0, 1 - y * y))
  const phi = (index % safeTotal) * increment
  return {
    x: Math.cos(phi) * distance * radius,
    y: y * radius,
    z: Math.sin(phi) * distance * radius,
  }
}

function ellipsePoint(radiusX, radiusY, axis, angle) {
  if (axis === 'x') {
    return new THREE.Vector3(0, Math.cos(angle) * radiusX, Math.sin(angle) * radiusY)
  }
  if (axis === 'z') {
    return new THREE.Vector3(Math.cos(angle) * radiusX, Math.sin(angle) * radiusY, 0)
  }
  return new THREE.Vector3(Math.cos(angle) * radiusX, 0, Math.sin(angle) * radiusY)
}

function makeEllipseLoop(radiusX, radiusY, axis = 'y', segments = 160) {
  const points = []
  for (let index = 0; index <= segments; index += 1) {
    const angle = (index / segments) * Math.PI * 2
    points.push(ellipsePoint(radiusX, radiusY, axis, angle))
  }
  return new THREE.BufferGeometry().setFromPoints(points)
}

function buildMarketMembraneGroup() {
  const group = new THREE.Group()
  group.name = 'marketMembrane'

  const buildField = ({ name, count, dims, size, opacity, palette = [] }) => {
    const positions = new Float32Array(count * 3)
    const colors = new Float32Array(count * 3)
    const colorStops = palette.map(value => new THREE.Color(value))

    for (let index = 0; index < count; index += 1) {
      const point = fibonacciSpherePoint(index, count, 1)
      const wave = Math.sin(index * 0.173) * 0.06 + Math.cos(index * 0.119) * 0.04
      const stretch = 1 + wave
      positions[index * 3] = point.x * dims.x * stretch
      positions[index * 3 + 1] = point.y * dims.y * (1 + wave * 0.55)
      positions[index * 3 + 2] = point.z * dims.z * stretch

      const blend = (Math.sin(index * 0.097) + 1) * 0.5
      const base = colorStops[index % colorStops.length]?.clone() || new THREE.Color('#72e5ff')
      const target = colorStops[(index + 1) % colorStops.length]?.clone() || new THREE.Color('#f7c76f')
      const mixed = base.lerp(target, blend)
      colors[index * 3] = mixed.r
      colors[index * 3 + 1] = mixed.g
      colors[index * 3 + 2] = mixed.b
    }

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))

    const material = new THREE.PointsMaterial({
      size,
      vertexColors: true,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    })
    const field = new THREE.Points(geometry, material)
    field.name = name
    field.userData.baseOpacity = opacity
    field.userData.axisDrift = 0.00012 + (size * 0.00002)
    return field
  }

  const outerShell = buildField({
    name: 'membraneOuter',
    count: MARKET_MEMBRANE_CONFIG.shellPoints,
    dims: MARKET_MEMBRANE_CONFIG.outer,
    size: 1.86,
    opacity: 0.18,
    palette: ['#f7fdff', '#dff8ff', '#e9f4ff', '#ffffff'],
  })
  const innerShell = buildField({
    name: 'membraneInner',
    count: MARKET_MEMBRANE_CONFIG.corePoints,
    dims: MARKET_MEMBRANE_CONFIG.inner,
    size: 1.32,
    opacity: 0.14,
    palette: ['#ffffff', '#e5f8ff', '#eef7ff'],
  })
  const pulseShell = buildField({
    name: 'membranePulse',
    count: MARKET_MEMBRANE_CONFIG.pulsePoints,
    dims: {
      x: MARKET_MEMBRANE_CONFIG.inner.x * 0.88,
      y: MARKET_MEMBRANE_CONFIG.inner.y * 0.72,
      z: MARKET_MEMBRANE_CONFIG.inner.z * 0.88,
    },
    size: 2.6,
    opacity: 0.18,
    palette: ['#dff8ff', '#ffffff', '#cfefff'],
  })

  group.add(outerShell, innerShell, pulseShell)
  group.userData.baseScale = 1
  return group
}

function buildCognitiveStormGroup() {
  const group = new THREE.Group()
  group.name = 'cognitiveStorm'

  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(14, 1),
    new THREE.MeshBasicMaterial({
      color: new THREE.Color('#020611'),
      transparent: true,
      opacity: 0.92,
      depthWrite: false,
    }),
  )
  core.name = 'stormCore'
  group.add(core)

  const halo = new THREE.Mesh(
    new THREE.TorusGeometry(22, 1.8, 10, 80),
    new THREE.MeshBasicMaterial({
      color: new THREE.Color('#7fe5ff'),
      transparent: true,
      opacity: 0.18,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  )
  halo.rotation.x = Math.PI / 2
  halo.name = 'stormHalo'
  group.add(halo)

  const armMaterials = []
  for (let arm = 0; arm < COGNITIVE_STORM_CONFIG.armCount; arm += 1) {
    const points = []
    const armOffset = (arm / COGNITIVE_STORM_CONFIG.armCount) * Math.PI * 2
    for (let index = 0; index < COGNITIVE_STORM_CONFIG.armPoints; index += 1) {
      const t = index / (COGNITIVE_STORM_CONFIG.armPoints - 1)
      const angle = armOffset + t * Math.PI * 3.7
      const radius = 8 + t * COGNITIVE_STORM_CONFIG.baseRadius
      const z = Math.sin(t * Math.PI * 4 + armOffset) * (8 + t * 10)
      points.push(new THREE.Vector3(
        Math.cos(angle) * radius,
        Math.sin(angle) * radius * 0.82,
        z,
      ))
    }
    const material = new THREE.LineBasicMaterial({
      color: new THREE.Color(arm % 2 === 0 ? '#8de6ff' : '#b89dff'),
      transparent: true,
      opacity: 0.18,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      material,
    )
    line.name = `stormArm_${arm}`
    line.userData.baseOpacity = 0.18
    armMaterials.push(material)
    group.add(line)
  }

  const positions = new Float32Array(COGNITIVE_STORM_CONFIG.particleCount * 3)
  const colors = new Float32Array(COGNITIVE_STORM_CONFIG.particleCount * 3)
  for (let index = 0; index < COGNITIVE_STORM_CONFIG.particleCount; index += 1) {
    const t = index / Math.max(1, COGNITIVE_STORM_CONFIG.particleCount - 1)
    const armOffset = (index % COGNITIVE_STORM_CONFIG.armCount) / COGNITIVE_STORM_CONFIG.armCount * Math.PI * 2
    const angle = armOffset + t * Math.PI * 5.2
    const radius = 5 + Math.random() * COGNITIVE_STORM_CONFIG.baseRadius * (0.3 + t * 0.9)
    positions[index * 3] = Math.cos(angle) * radius
    positions[index * 3 + 1] = Math.sin(angle) * radius * 0.78
    positions[index * 3 + 2] = (Math.random() - 0.5) * 28
    const mix = index % 3 === 0 ? new THREE.Color('#ffffff') : index % 2 === 0 ? new THREE.Color('#8ce8ff') : new THREE.Color('#ba9dff')
    colors[index * 3] = mix.r
    colors[index * 3 + 1] = mix.g
    colors[index * 3 + 2] = mix.b
  }
  const cloudGeometry = new THREE.BufferGeometry()
  cloudGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  cloudGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const cloudMaterial = new THREE.PointsMaterial({
    size: 2.15,
    vertexColors: true,
    transparent: true,
    opacity: 0.3,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  })
  const cloud = new THREE.Points(cloudGeometry, cloudMaterial)
  cloud.name = 'stormCloud'
  group.add(cloud)

  group.userData.armMaterials = armMaterials
  group.userData.cloudMaterial = cloudMaterial
  group.userData.coreMaterial = core.material
  group.userData.haloMaterial = halo.material
  return group
}

function buildDenseShellPositions(nodes, focus = {}) {
  if (!nodes.length) return new Map()

  const focusTicker = focus.selectedTicker || focus.targetTicker || ''
  const focusSector = focus.focusSector || ''
  const positions = new Map()

  const sectorBuckets = new Map()
  nodes.forEach(node => {
    const key = node?.sector || 'unknown'
    const bucket = sectorBuckets.get(key) || []
    bucket.push(node)
    sectorBuckets.set(key, bucket)
  })
  const sectorKeys = [...sectorBuckets.keys()].sort()
  const sectorAnchors = new Map(
    sectorKeys.map((sector, index) => {
      const ratio = index / Math.max(1, sectorKeys.length)
      const angle = ratio * Math.PI * 2 + ((hashCode(sector) % 23) - 11) * 0.012
      const lift = Math.sin(angle * 1.7) * 68 + ((hashCode(sector) % 9) - 4) * 5
      return [sector, new THREE.Vector3(
        Math.cos(angle) * DENSE_SHELL_LAYOUT.shellRadiusX * 0.42,
        lift,
        Math.sin(angle) * DENSE_SHELL_LAYOUT.shellRadiusZ * 0.42,
      )]
    }),
  )

  const ordered = [...nodes].sort((a, b) => {
    const aId = a?.id || a?.ticker || ''
    const bId = b?.id || b?.ticker || ''
    const aPrimary = aId === focusTicker ? 1 : 0
    const bPrimary = bId === focusTicker ? 1 : 0
    if (aPrimary !== bPrimary) return bPrimary - aPrimary
    const aFocus = Number(Boolean(a?.hasSpark)) + Number(Boolean(focusSector && a?.sector === focusSector))
    const bFocus = Number(Boolean(b?.hasSpark)) + Number(Boolean(focusSector && b?.sector === focusSector))
    if (aFocus !== bFocus) return bFocus - aFocus
    return hashCode(aId) - hashCode(bId)
  })

  ordered.forEach((node, index) => {
    const id = node?.id || node?.ticker || ''
    const sector = node?.sector || 'unknown'
    const basePoint = fibonacciSpherePoint(index, ordered.length, 1)
    const shellVec = new THREE.Vector3(
      basePoint.x * DENSE_SHELL_LAYOUT.shellRadiusX,
      basePoint.y * DENSE_SHELL_LAYOUT.shellRadiusY,
      basePoint.z * DENSE_SHELL_LAYOUT.shellRadiusZ,
    )
    const radial = shellVec.clone().normalize()
    const tangentA = new THREE.Vector3(-radial.z, 0, radial.x)
    if (tangentA.lengthSq() < 0.001) tangentA.set(1, 0, 0)
    tangentA.normalize()
    const tangentB = new THREE.Vector3().crossVectors(radial, tangentA).normalize()

    const sectorAnchor = sectorAnchors.get(sector) || new THREE.Vector3()
    const sectorHash = hashCode(sector)
    const idHash = hashCode(id)
    const driftA = ((idHash % 17) - 8) * 3.1
    const driftB = ((idHash % 13) - 6) * 2.7
    const vec = shellVec
      .lerp(sectorAnchor.clone().addScaledVector(radial, DENSE_SHELL_LAYOUT.shellDrift), 0.38)
      .addScaledVector(tangentA, driftA + ((sectorHash % 7) - 3) * DENSE_SHELL_LAYOUT.sectorSpread * 0.2)
      .addScaledVector(tangentB, driftB)

    const isPrimary = id === focusTicker
    const isFocusRelated = isPrimary || Boolean(node?.hasSpark) || (focusSector && sector === focusSector)
    if (isPrimary) {
      vec.set(
        DENSE_SHELL_LAYOUT.lateralBias - 36,
        DENSE_SHELL_LAYOUT.focusLift,
        DENSE_SHELL_LAYOUT.focusDepth,
      )
    } else if (isFocusRelated) {
      vec.multiplyScalar(DENSE_SHELL_LAYOUT.focusScale)
      vec.x += DENSE_SHELL_LAYOUT.lateralBias
      vec.z += 52
    } else {
      vec.x += DENSE_SHELL_LAYOUT.lateralBias
      vec.y *= 0.94
    }

    positions.set(id, {
      x: vec.x,
      y: vec.y,
      z: vec.z,
    })
  })

  return positions
}

function parseHudIntentFromHash(hash = window.location.hash) {
  // Try hash first: #hud?ticker=SXTX&source=scanner
  if (hash && hash.startsWith('#hud')) {
    const [, query = ''] = hash.split('?')
    const params = new URLSearchParams(query)
    const ticker = (params.get('ticker') || '').trim().toUpperCase()
    if (ticker) {
      return {
        ticker,
        source: (params.get('source') || 'direct').trim().toLowerCase(),
        rank: (params.get('rank') || '').trim(),
        score: (params.get('score') || '').trim(),
        form: (params.get('form') || '').trim().toUpperCase(),
        reason: compactReason(params.get('reason') || ''),
        channel: (params.get('channel') || '').trim().toLowerCase(),
        returnTo: (params.get('return_to') || '').trim(),
      }
    }
  }
  // Fallback: ?ticker=SXTX query param (direct URL)
  if (typeof window !== 'undefined') {
    const qp = new URLSearchParams(window.location.search)
    const ticker = (qp.get('ticker') || '').trim().toUpperCase()
    if (ticker) {
      return {
        ticker,
        source: (qp.get('source') || 'direct').trim().toLowerCase(),
        rank: (qp.get('rank') || '').trim(),
        score: (qp.get('score') || '').trim(),
        form: (qp.get('form') || '').trim().toUpperCase(),
        reason: compactReason(qp.get('reason') || ''),
        channel: (qp.get('channel') || '').trim().toLowerCase(),
        returnTo: (qp.get('return_to') || '').trim(),
      }
    }
  }
  return null
}

// ── Status bar ────────────────────────────────────────────────────────────────
function StatusBar({ nodeCount, filteredCount, activeSparkCount, sparkRate, lastEventAge, wsStatus, macroData }) {
  const mult = macroData?.macro_pressure?.global_multiplier ?? 1.0
  const recession = macroData?.macro_pressure?.recession_warning ?? false
  const multColor = mult >= 1.05 ? 'var(--hud-success)' : mult <= 0.92 ? 'var(--hud-danger)' : 'var(--hud-warning)'

  const segmentStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
    borderRadius: 999,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.03)',
    fontFamily: HUD_FONTS.mono,
    fontSize: 10,
    color: 'var(--hud-muted)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  }

  return (
    <div style={{
      position: 'fixed', top: 12, left: 16, right: 16, minHeight: 52,
      ...glassPanel('rgba(215, 180, 106, 0.18)', 'rgba(114, 229, 255, 0.08)'),
      borderRadius: 20,
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
      fontSize: 11, color: 'var(--hud-muted)', zIndex: 300,
      userSelect: 'none', flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, marginRight: 4 }}>
        <div style={{
          width: 34, height: 34, borderRadius: 12,
          background: 'radial-gradient(circle at 35% 35%, rgba(114,229,255,0.18), rgba(215,180,106,0.14) 46%, rgba(8,10,16,0.92) 100%)',
          border: '1px solid rgba(114,229,255,0.18)',
          display: 'grid', placeItems: 'center',
          boxShadow: '0 0 18px rgba(114,229,255,0.14)',
        }}>
          <span style={{ ...monoLabel, fontSize: 10, color: 'var(--hud-cyan)' }}>CB</span>
        </div>
        <div>
          <div style={{ color: 'var(--hud-text)', fontWeight: 700, fontFamily: HUD_FONTS.display, fontSize: 16, lineHeight: 1 }}>Cerebro</div>
          <div style={{ ...monoLabel, fontSize: 8, color: 'var(--hud-muted)' }}>economic nervous system</div>
        </div>
      </div>

      <span style={segmentStyle}>visible <b style={{ color: 'var(--hud-text)' }}>{filteredCount.toLocaleString()}</b><span style={{ color: 'rgba(158,168,186,0.72)' }}>/{nodeCount.toLocaleString()}</span></span>
      <span style={segmentStyle}>active now <b style={{ color: activeSparkCount > 0 ? 'var(--hud-cyan)' : 'var(--hud-muted)' }}>{activeSparkCount}</b></span>
      <span style={segmentStyle}>events/min <b style={{ color: sparkRate > 0 ? 'var(--hud-success)' : 'var(--hud-muted)' }}>{sparkRate}</b></span>
      <span style={segmentStyle}>last spark <b style={{ color: lastEventAge === '—' ? 'var(--hud-muted)' : 'var(--hud-text)' }}>{lastEventAge}</b></span>
      <span style={{ ...segmentStyle, color: wsStatus === 'connected' ? 'var(--hud-success)' : wsStatus === 'reconnecting' ? 'var(--hud-warning)' : 'var(--hud-danger)' }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor', boxShadow: wsStatus === 'connected' ? '0 0 10px currentColor' : 'none' }} />
        {wsStatus}
      </span>
      <span style={segmentStyle}>p_macro <b style={{ color: multColor }}>{mult.toFixed(3)}x</b></span>

      {recession && (
        <span style={{ ...segmentStyle, color: 'var(--hud-danger)', borderColor: 'rgba(255,134,134,0.24)', background: 'rgba(255,134,134,0.08)' }}>
          recession watch
        </span>
      )}

      <span style={{ marginLeft: 'auto', ...monoLabel, fontSize: 8, color: 'rgba(202,184,149,0.72)' }}>
        operator telemetry
      </span>
    </div>
  )
}

function VisorOverlay({ marketPulse, targetLock, activeTargetNode, activeSparkCount, cognitiveLoad, sympathyTotal }) {
  const palettes = {
    bullish: {
      accent: 'var(--hud-success)',
      secondary: 'var(--hud-cyan)',
      frame: 'rgba(95,208,170,0.24)',
      frameGlow: 'rgba(95,208,170,0.14)',
      fieldGlow: 'radial-gradient(circle at 50% 50%, rgba(95,208,170,0.14) 0%, rgba(114,229,255,0.08) 34%, rgba(114,229,255,0) 70%)',
      label: 'bull pressure',
    },
    bearish: {
      accent: 'var(--hud-danger)',
      secondary: 'var(--hud-warning)',
      frame: 'rgba(255,122,144,0.24)',
      frameGlow: 'rgba(255,122,144,0.14)',
      fieldGlow: 'radial-gradient(circle at 50% 50%, rgba(255,122,144,0.14) 0%, rgba(255,191,105,0.08) 34%, rgba(255,191,105,0) 70%)',
      label: 'bear pressure',
    },
    quiet: {
      accent: 'var(--hud-gold)',
      secondary: 'var(--hud-cyan)',
      frame: 'rgba(215,180,106,0.18)',
      frameGlow: 'rgba(215,180,106,0.08)',
      fieldGlow: 'radial-gradient(circle at 50% 50%, rgba(215,180,106,0.12) 0%, rgba(114,229,255,0.04) 34%, rgba(114,229,255,0) 70%)',
      label: 'latent field',
    },
    balanced: {
      accent: 'var(--hud-gold)',
      secondary: 'var(--hud-cyan)',
      frame: 'rgba(114,229,255,0.2)',
      frameGlow: 'rgba(114,229,255,0.08)',
      fieldGlow: 'radial-gradient(circle at 50% 50%, rgba(114,229,255,0.12) 0%, rgba(215,180,106,0.08) 34%, rgba(114,229,255,0) 70%)',
      label: 'balanced tape',
    },
  }
  const palette = palettes[marketPulse.bias] || palettes.balanced
  const activeLabel = targetLock.phase !== 'idle'
    ? `${targetLock.phase} · ${targetLock.ticker}`
    : activeTargetNode?.id
      ? `track ${activeTargetNode.id}`
      : marketPulse.hottestTicker
        ? `watch ${marketPulse.hottestTicker}`
        : 'field standby'
  const heartbeatMs = Math.max(980 - marketPulse.intensity * 380, 520)
  const bullRatio = marketPulse.total > 0 ? marketPulse.positive / marketPulse.total : 0
  const bearRatio = marketPulse.total > 0 ? marketPulse.negative / marketPulse.total : 0
  const intensityPct = `${Math.max(14, Math.round(marketPulse.intensity * 100))}%`
  const loadTone = cognitiveLoad > 80 ? 'var(--hud-danger)' : cognitiveLoad > 50 ? 'var(--hud-gold)' : 'var(--hud-cyan)'

  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 180 }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        background: palette.fieldGlow,
        mixBlendMode: 'screen',
        opacity: 0.86,
      }} />
      <div style={{
        position: 'absolute',
        left: '7%',
        top: '18%',
        bottom: '18%',
        width: 104,
        background: `linear-gradient(90deg, rgba(0,0,0,0) 0%, ${POLARITY_FIELD_COLORS.bullish} 100%)`,
        opacity: 0.018 + bullRatio * 0.08,
        filter: 'blur(34px)',
        transform: 'skewY(-9deg)',
        mixBlendMode: 'screen',
      }} />
      <div style={{
        position: 'absolute',
        right: '7%',
        top: '18%',
        bottom: '18%',
        width: 104,
        background: `linear-gradient(270deg, rgba(0,0,0,0) 0%, ${POLARITY_FIELD_COLORS.bearish} 100%)`,
        opacity: 0.018 + bearRatio * 0.08,
        filter: 'blur(34px)',
        transform: 'skewY(9deg)',
        mixBlendMode: 'screen',
      }} />

      <div style={{
        position: 'absolute',
        inset: 14,
        borderRadius: 34,
        border: `1px solid ${palette.frame}`,
        boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.02), 0 0 34px ${palette.frameGlow}`,
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 16%, transparent 82%, rgba(255,255,255,0.025) 100%)',
        }} />
        <div style={{
          position: 'absolute',
          left: 28,
          right: 28,
          top: 24,
          height: 1,
          background: `linear-gradient(90deg, transparent 0%, ${palette.frame} 18%, transparent 58%)`,
          opacity: 0.8,
        }} />
        <div style={{
          position: 'absolute',
          left: 28,
          right: 28,
          bottom: 24,
          height: 1,
          background: `linear-gradient(90deg, transparent 42%, ${palette.frame} 78%, transparent 100%)`,
          opacity: 0.7,
        }} />
      </div>

      <div style={{
        position: 'absolute',
        left: '50%',
        top: '53%',
        width: 'min(54vw, 860px)',
        height: 'min(58vh, 620px)',
        transform: 'translate(-50%, -50%)',
        borderRadius: '50%',
        border: `1px solid ${palette.frame}`,
        boxShadow: `0 0 42px ${palette.frameGlow}, inset 0 0 0 1px rgba(255,255,255,0.02)`,
        opacity: 0.5,
      }}>
        <div style={{
          position: 'absolute',
          inset: '11%',
          borderRadius: '50%',
          border: `1px dashed ${palette.frame}`,
          opacity: 0.45,
          animation: 'hudVisorSpin 26s linear infinite',
        }} />
        <div style={{
          position: 'absolute',
          inset: '22%',
          borderRadius: '50%',
          border: `1px solid ${palette.frame}`,
          opacity: 0.32,
          animation: `hudVisorBreath ${heartbeatMs}ms ease-in-out infinite`,
        }} />
        <div style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          width: '26%',
          height: '26%',
          transform: 'translate(-50%, -50%)',
          borderRadius: '50%',
          border: `1px solid ${palette.secondary}`,
          boxShadow: `0 0 22px ${palette.frameGlow}`,
          opacity: 0.34,
        }} />
        {[
          { left: '17%', top: '17%', rotate: '-6deg' },
          { right: '17%', top: '17%', rotate: '6deg' },
          { left: '17%', bottom: '17%', rotate: '6deg' },
          { right: '17%', bottom: '17%', rotate: '-6deg' },
        ].map((corner, index) => (
          <div
            key={index}
            style={{
              position: 'absolute',
              width: 70,
              height: 70,
              borderTop: `1px solid ${palette.frame}`,
              borderLeft: `1px solid ${palette.frame}`,
              opacity: 0.34,
              boxShadow: `0 0 22px ${palette.frameGlow}`,
              transform: `rotate(${corner.rotate})`,
              ...corner,
            }}
          />
        ))}
      </div>

      <div style={{
        position: 'absolute',
        left: '50%',
        bottom: 30,
        transform: 'translateX(-50%)',
        width: 'min(54vw, 920px)',
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        gap: 10,
        padding: '10px 12px',
        borderRadius: 22,
        border: `1px solid ${palette.frame}`,
        background: 'linear-gradient(180deg, rgba(10,14,22,0.62), rgba(7,10,16,0.36))',
        boxShadow: `0 18px 40px rgba(0,0,0,0.24), 0 0 24px ${palette.frameGlow}`,
        backdropFilter: 'blur(16px)',
      }}>
        {[
          ['field bias', palette.label],
          ['sympathy lanes', String(sympathyTotal)],
          ['cognitive load', `${Math.round(cognitiveLoad)}%`],
          ['target rail', activeLabel],
        ].map(([label, value], index) => (
          <div key={label} style={{
            minWidth: 0,
            padding: '8px 10px',
            borderRadius: 16,
            background: 'rgba(255,255,255,0.03)',
            border: `1px solid ${index === 2 ? loadTone : 'rgba(255,255,255,0.06)'}`,
          }}>
            <div style={{ ...monoLabel, fontSize: 7, color: index === 2 ? loadTone : 'var(--hud-muted)' }}>{label}</div>
            <div style={{
              marginTop: 6,
              color: index === 0 ? palette.accent : index === 2 ? loadTone : 'var(--hud-text)',
              fontFamily: HUD_FONTS.display,
              fontSize: label === 'target rail' ? 13 : 15,
              fontWeight: 700,
              letterSpacing: '-0.03em',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      <div style={{
        position: 'absolute',
        left: '50%',
        bottom: 108,
        transform: 'translateX(-50%)',
        width: 'min(38vw, 560px)',
        height: 8,
        borderRadius: 999,
        overflow: 'hidden',
        border: `1px solid ${palette.frame}`,
        background: 'rgba(255,255,255,0.03)',
        boxShadow: `0 0 18px ${palette.frameGlow}`,
      }}>
        <div style={{
          width: intensityPct,
          height: '100%',
          borderRadius: 999,
          background: `linear-gradient(90deg, transparent 0%, ${palette.secondary} 18%, ${palette.accent} 74%, transparent 100%)`,
          boxShadow: `0 0 14px ${palette.frameGlow}`,
          animation: `hudHeartbeatTrace ${heartbeatMs}ms ease-in-out infinite`,
        }} />
      </div>

      <div style={{
        position: 'absolute',
        left: '50%',
        bottom: 126,
        transform: 'translateX(-50%)',
        color: 'var(--hud-muted)',
        fontFamily: HUD_FONTS.mono,
        fontSize: 8,
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        opacity: 0.78,
      }}>
        cognitive visor · tactical atmosphere
      </div>
    </div>
  )
}

// ── Weather Shock Overlay ─────────────────────────────────────────────────────

function WeatherShockOverlay({ shock }) {
  const isDisrupt = shock.type === 'disruption'
  const col   = isDisrupt ? '#ef4444' : '#10b981'
  const icon  = isDisrupt ? '🌩' : '🟢'
  const surfaceBackground = isDisrupt
    ? 'linear-gradient(180deg, rgba(239,68,68,0.16) 0%, rgba(9,14,22,0.86) 100%)'
    : 'linear-gradient(180deg, rgba(16,185,129,0.16) 0%, rgba(9,14,22,0.86) 100%)'
  const surfaceBorder = isDisrupt ? 'rgba(239,68,68,0.34)' : 'rgba(16,185,129,0.34)'
  const surfaceGlow = isDisrupt ? 'rgba(239,68,68,0.12)' : 'rgba(16,185,129,0.12)'

  return (
    <div style={{
      position: 'fixed',
      left: 22,
      bottom: 28,
      zIndex: 320,
      pointerEvents: 'none',
      fontFamily: "'Courier New', monospace",
      animation: 'weatherSignalOut 8s ease forwards',
    }}>
      <div style={{
        width: 300,
        padding: '12px 14px 13px',
        borderRadius: 18,
        border: `1px solid ${surfaceBorder}`,
        background: surfaceBackground,
        backdropFilter: 'blur(18px)',
        boxShadow: `0 18px 42px rgba(0,0,0,0.34), 0 0 0 1px rgba(255,255,255,0.03), 0 0 26px ${surfaceGlow}`,
      }} />

      <div style={{
        position: 'absolute',
        left: 14,
        right: 14,
        top: 12,
        height: 2,
        borderRadius: 999,
        background: `linear-gradient(90deg, transparent 0%, ${col} 16%, ${col} 84%, transparent 100%)`,
        boxShadow: `0 0 14px ${col}55`,
        opacity: 0.74,
        animation: 'stormRail 2.6s ease-in-out infinite',
      }} />

      <div style={{
        position: 'absolute',
        left: 16,
        top: 24,
        width: 10,
        height: 10,
        borderRadius: '50%',
        background: col,
        boxShadow: `0 0 18px ${col}`,
        animation: 'stormDot 1.9s ease-in-out infinite',
      }} />

      <div style={{
        position: 'relative',
        paddingTop: 12,
      }}>
        <div style={{
          color: col,
          fontSize: 9,
          letterSpacing: 3,
          marginBottom: 7,
          textTransform: 'uppercase',
        }}>
          {icon} {isDisrupt ? 'Weather pressure lane' : 'Weather recovery lane'}
        </div>
        <div style={{ color: '#ddeeff', fontSize: 13, fontWeight: 700, letterSpacing: 0.4 }}>
          {shock.eventName || (isDisrupt ? 'SEVERE WEATHER' : 'RECOVERY DEMAND')}
        </div>
        <div style={{ color: '#93a6ba', fontSize: 10, marginTop: 5, lineHeight: 1.6 }}>
          {shock.severity ? `Severity ${shock.severity.toUpperCase()}` : 'Field pressure detected'}
          {shock.stateCode ? ` · Zone ${shock.stateCode}` : ''}
          {shock.nodeCount > 0 ? ` · ${shock.nodeCount} node${shock.nodeCount !== 1 ? 's' : ''} affected` : ''}
        </div>
      </div>

      <style>{`
        @keyframes weatherSignalOut {
          0%, 55% { opacity: 1; }
          100%    { opacity: 0; }
        }
        @keyframes stormRail {
          0%, 100% { opacity: 0.52; transform: scaleX(0.96); }
          50% { opacity: 0.88; transform: scaleX(1); }
        }
        @keyframes stormDot {
          0%, 100% { transform: scale(0.94); opacity: 0.64; }
          50% { transform: scale(1.08); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

// ── Main HUD ──────────────────────────────────────────────────────────────────
export default function CerebroHUD() {
  const [rawNodes,    setRawNodes]    = useState([])
  const [macroData,   setMacroData]   = useState(null)
  const [wsStatus,    setWsStatus]    = useState('connecting')
  const [liveSparks,  setLiveSparks]  = useState([])
  const [selectedTicker, setSelectedTicker] = useState('')
  const [handoffIntent, setHandoffIntent] = useState(() => parseHudIntentFromHash())
  const [targetLock, setTargetLock] = useState(() => ({ ...TARGET_LOCK_IDLE }))
  const [scannerReturnUrl, setScannerReturnUrl] = useState(() => {
    if (typeof window === 'undefined') return ''
    try {
      return window.sessionStorage.getItem(SCANNER_RETURN_STORAGE_KEY) || ''
    } catch {
      return ''
    }
  })
  const [focusStatus, setFocusStatus] = useState(null)
  const [lockImpact, setLockImpact] = useState(0)
  const [lockImpactMeta, setLockImpactMeta] = useState({ ticker: '', source: 'graph' })
  const [searchTicker, setSearchTicker] = useState('')
  const [weatherShock,   setWeatherShock]  = useState(null)
  const [cognitiveLoad,  setCognitiveLoad] = useState(0)
  const [isDeepBlue,     setIsDeepBlue]    = useState(false)
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)
  const [topNavOpen, setTopNavOpen] = useState(true)
  const [filters, setFilters] = useState({
    sector: 'ALL', minGravity: 1, minBrightness: 0, sparksOnly: false, sympathyShield: true,
  })

  const fgRef            = useRef(null)
  const graphRef         = fgRef
  const graphCanvasShellRef = useRef(null)
  const commandCardRef = useRef(null)
  const activeTargetCardRef = useRef(null)
  const initialCameraSettledRef = useRef(false)
  const leftSidebarOpenRef = useRef(true)
  const rightSidebarOpenRef = useRef(true)
  const topNavOpenRef = useRef(true)
  const leftSidebarNodeRef = useRef(null)
  const rightSidebarNodeRef = useRef(null)
  const topNavNodeRef = useRef(null)
  const nodeMapRef       = useRef({})
  const animFrameRef     = useRef(null)
  const bloomImpulseRef  = useRef(0)
  const clockRef         = useRef(0)
  const renderProfileRef = useRef(HUD_RENDER_PROFILES.cinematic)
  const displayedNodesRef = useRef([])
  const denseFixedNodeIdsRef = useRef(new Set())
  const weatherTimerRef  = useRef(null)
  const targetMarkerRef  = useRef(null)
  const targetNodeRef    = useRef(null)
  const mousePosRef      = useRef({ x: 0, y: 0 })
  const weatherLinesRef  = useRef(null)   // THREE.Group of tether lines
  const weatherDecayRef  = useRef(0)      // current line opacity (1→0 over ~4 min)
  const isDeepBlueRef    = useRef(false)  // bridge: React state → animation loop
  const etfCablesRef     = useRef([])     // active ETF tether cable meshes
  const orbitingPeersRef = useRef([])     // competitor nodes currently in orbit
  const gravityRingsRef  = useRef([])     // concentric ring groups (center + peers)
  const gammaWellsRef    = useRef([])     // options gamma well meshes
  const focusRequestTimerRef = useRef(null)
  const focusStatusTimerRef = useRef(null)
  const lockSettleTimerRef = useRef(null)
  const lockImpactTimerRef = useRef(null)
  const preLockFiltersRef = useRef(null)
  const handoffConsumedRef = useRef('')
  const settledTargetRef = useRef('')
  const cameraFlightRef = useRef(null)   // active RAF camera flight { id, ticker }
  const selectedTickerRef = useRef('')
  const targetLockRef = useRef(TARGET_LOCK_IDLE)
  const filtersRef = useRef(filters)
  const marketPulseRef = useRef({ bias: 'balanced', intensity: 0.2, total: 0, positive: 0, negative: 0 })
  const hoverMagnetRef = useRef({ node: null, ts: 0 })
  const interactionFreezeUntilRef = useRef(0)
  const lastNodeClickAtRef = useRef(0)
  const lockCueRef = useRef({ phase: 'idle', ticker: '' })
  const lockPillarRef = useRef(null)      // scene-level light-pillar beam through selected node
  const pinnedNodeRef = useRef(null)      // node currently fx/fy/fz locked to camera focus
  const [visitHistory, setVisitHistory] = useState([])  // last N selected tickers (newest first)
  const audioContextRef = useRef(null)
  const audioReadyRef = useRef(false)
  const [hoverData,      setHoverData]      = useState(null)   // { node, x, y }
  const [weatherTrigger, setWeatherTrigger] = useState(0)      // inc on weather event
  useEffect(() => {
    const onHashChange = () => setHandoffIntent(parseHudIntentFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const consumeHandoffHash = useCallback(() => {
    if (typeof window === 'undefined') return
    const cleanHash = '#hud'
    // Strip handoff query params (ticker, source, rank, score, form, reason, channel, return_to)
    // after they have been consumed so back/forward nav does not re-fire the handoff.
    const handoffKeys = ['ticker', 'source', 'rank', 'score', 'form', 'reason', 'channel', 'return_to']
    let nextSearch = window.location.search
    if (nextSearch) {
      const sp = new URLSearchParams(nextSearch)
      let changed = false
      handoffKeys.forEach(k => {
        if (sp.has(k)) { sp.delete(k); changed = true }
      })
      if (changed) {
        const s = sp.toString()
        nextSearch = s ? `?${s}` : ''
      }
    }
    if (window.location.hash !== cleanHash || nextSearch !== window.location.search) {
      const nextUrl = `${window.location.pathname}${nextSearch}${cleanHash}`
      window.history.replaceState(null, '', nextUrl)
    }
    setHandoffIntent(null)
  }, [])

  const resolveScannerReturnUrl = useCallback((intent = null) => {
    const explicit = String(intent?.returnTo || '').trim()
    if (/^https?:\/\//i.test(explicit)) return explicit
    if (typeof document !== 'undefined') {
      const referrer = String(document.referrer || '').trim()
      if (/catalystedgescanner\.com/i.test(referrer)) return referrer
    }
    return SCANNER_HOME_URL
  }, [])

  useEffect(() => {
    if (!handoffIntent?.ticker) return
    if ((handoffIntent.source || '').toLowerCase() !== 'scanner') return
    setScannerReturnUrl(resolveScannerReturnUrl(handoffIntent))
  }, [handoffIntent, resolveScannerReturnUrl])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      if (scannerReturnUrl) {
        window.sessionStorage.setItem(SCANNER_RETURN_STORAGE_KEY, scannerReturnUrl)
      } else {
        window.sessionStorage.removeItem(SCANNER_RETURN_STORAGE_KEY)
      }
    } catch {
      // ignore sessionStorage access failures
    }
  }, [scannerReturnUrl])

  const ensureAudioContext = useCallback(() => {
    if (typeof window === 'undefined') return null
    const AudioCtor = window.AudioContext || window.webkitAudioContext
    if (!AudioCtor) return null
    if (!audioContextRef.current) audioContextRef.current = new AudioCtor()
    return audioContextRef.current
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const unlockAudio = () => {
      const ctx = ensureAudioContext()
      if (!ctx) return
      audioReadyRef.current = true
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    }
    window.addEventListener('pointerdown', unlockAudio, { passive: true })
    window.addEventListener('keydown', unlockAudio)
    return () => {
      window.removeEventListener('pointerdown', unlockAudio)
      window.removeEventListener('keydown', unlockAudio)
    }
  }, [ensureAudioContext])

  const playTargetCue = useCallback((phase) => {
    const cue = TARGET_LOCK_PHASE_STYLE[phase]?.audio
    if (!cue || !audioReadyRef.current) return
    const ctx = ensureAudioContext()
    if (!ctx) return
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {})
      if (ctx.state === 'suspended') return
    }
    const now = ctx.currentTime + 0.01
    cue.tones.forEach((freq, index) => {
      const osc = ctx.createOscillator()
      const filter = ctx.createBiquadFilter()
      const gain = ctx.createGain()
      const start = now + index * (cue.spacing || 0.05)
      const end = start + (cue.duration || 0.1)
      osc.type = cue.wave || 'triangle'
      osc.frequency.setValueAtTime(freq, start)
      if (cue.sweep?.[index] != null) {
        osc.frequency.linearRampToValueAtTime(cue.sweep[index], end)
      }
      filter.type = 'lowpass'
      filter.frequency.setValueAtTime(cue.filter || 1400, start)
      gain.gain.setValueAtTime(0.0001, start)
      gain.gain.linearRampToValueAtTime(cue.gain || 0.012, start + Math.min(0.02, (cue.duration || 0.1) * 0.26))
      gain.gain.exponentialRampToValueAtTime(0.0001, end)
      osc.connect(filter)
      filter.connect(gain)
      gain.connect(ctx.destination)
      osc.start(start)
      osc.stop(end + 0.025)
    })
  }, [ensureAudioContext])

  const flashFocusStatus = useCallback((message, tone = 'lock') => {
    if (focusStatusTimerRef.current) clearTimeout(focusStatusTimerRef.current)
    setFocusStatus({ message, tone })
    const hold = tone === 'error' ? 3600 : tone === 'scan' ? 1500 : tone === 'settle' ? 1700 : 2400
    focusStatusTimerRef.current = setTimeout(() => setFocusStatus(null), hold)
  }, [])

  const applyCameraFocusFrame = useCallback((active) => {
    const camera = graphRef.current?.camera?.()
    if (!camera) return
    // Clear any stale view offset — sidebar-aware centering is now handled
    // by panning camera+target in focusCameraToTicker instead of setViewOffset
    if (camera.view) camera.clearViewOffset()
    camera.updateProjectionMatrix()
  }, [])

  const triggerLockImpact = useCallback((ticker, source = 'graph') => {
    if (lockImpactTimerRef.current) clearTimeout(lockImpactTimerRef.current)
    setLockImpactMeta({ ticker, source })
    setLockImpact(prev => prev + 1)
    bloomImpulseRef.current = Math.max(bloomImpulseRef.current, 1)
    lockImpactTimerRef.current = setTimeout(() => {
      setLockImpactMeta(current => current.ticker === ticker ? { ...current, ticker: '', source } : current)
    }, 480)
  }, [])

  const holdInteractionFrame = useCallback((duration = INTERACTION_ASSIST.hoverFreezeMs) => {
    const until = performance.now() + duration
    interactionFreezeUntilRef.current = Math.max(interactionFreezeUntilRef.current, until)
  }, [])

  useEffect(() => {
    targetLockRef.current = targetLock
  }, [targetLock])

  useEffect(() => {
    selectedTickerRef.current = selectedTicker
  }, [selectedTicker])

  useEffect(() => {
    filtersRef.current = filters
  }, [filters])

  useEffect(() => { leftSidebarOpenRef.current = leftSidebarOpen }, [leftSidebarOpen])
  useEffect(() => { rightSidebarOpenRef.current = rightSidebarOpen }, [rightSidebarOpen])
  useEffect(() => { topNavOpenRef.current = topNavOpen }, [topNavOpen])

  useEffect(() => {
    const framed = Boolean(selectedTicker || targetLock.phase !== 'idle')
    applyCameraFocusFrame(framed)
  }, [applyCameraFocusFrame, selectedTicker, targetLock.phase])

  // Re-center projection when sidebars toggle while a node is focused
  useEffect(() => {
    if (selectedTicker || targetLock.phase !== 'idle') {
      applyCameraFocusFrame(true)
    }
  }, [leftSidebarOpen, rightSidebarOpen, topNavOpen, applyCameraFocusFrame, selectedTicker, targetLock.phase])

  useEffect(() => {
    const handleResize = () => applyCameraFocusFrame(Boolean(selectedTicker || targetLockRef.current.phase !== 'idle'))
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [applyCameraFocusFrame, selectedTicker])

  useEffect(() => {
    const controls = graphRef.current?.controls?.()
    if (!controls) return
    const suppressNavigation = Boolean(hoverData?.node?.id) || targetLock.phase === 'acquiring' || targetLock.phase === 'settling'
    controls.enableRotate = !suppressNavigation
    controls.enablePan = !suppressNavigation
  }, [hoverData?.node?.id, targetLock.phase])

  useEffect(() => {
    if (!rawNodes.length || initialCameraSettledRef.current) return
    if (selectedTicker || targetLock.phase !== 'idle') return
    const fg = graphRef.current
    if (!fg?.zoomToFit) return

    const timer = setTimeout(() => {
      if (initialCameraSettledRef.current) return
      try {
        fg.zoomToFit(360, 80, node => Boolean(node?.id))
        const controls = fg.controls?.()
        if (controls) {
          controls.target.set(0, 0, 0)
          controls.update()
        }
        initialCameraSettledRef.current = true
      } catch (error) {
        console.warn('Initial camera fit skipped:', error)
      }
    }, 260)

    return () => clearTimeout(timer)
  }, [rawNodes.length, selectedTicker, targetLock.phase])

  useEffect(() => {
    const dom = graphRef.current?.renderer?.()?.domElement
    if (!dom) return
    dom.style.cursor = hoverData?.node?.id
      ? 'pointer'
      : targetLock.phase !== 'idle'
        ? 'default'
        : 'grab'
  }, [hoverData?.node?.id, targetLock.phase])

  useEffect(() => {
    const phase = targetLock.phase || 'idle'
    const ticker = targetLock.ticker || ''
    const last = lockCueRef.current
    if (last.phase === phase && last.ticker === ticker) return
    lockCueRef.current = { phase, ticker }
    if (phase !== 'idle') playTargetCue(phase)
  }, [playTargetCue, targetLock.phase, targetLock.ticker])

  useEffect(() => () => {
    if (focusRequestTimerRef.current) clearTimeout(focusRequestTimerRef.current)
    if (focusStatusTimerRef.current) clearTimeout(focusStatusTimerRef.current)
    if (lockSettleTimerRef.current) clearTimeout(lockSettleTimerRef.current)
    if (lockImpactTimerRef.current) clearTimeout(lockImpactTimerRef.current)
  }, [])

  // ── Load bedrock ──────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    const loadUniverse = async () => {
      try {
        const perPage = 12000
        let page = 1
        let pages = 1
        const tickersById = new Map()

        while (!cancelled && page <= pages) {
          const r = await fetch(`${API_BASE}/api/universe?per_page=${perPage}&page=${page}`)
          const data = await r.json()
          const tickers = Array.isArray(data) ? data : (data.tickers || [])

          tickers.forEach(t => {
            if (t?.ticker) tickersById.set(t.ticker, t)
          })

          if (Array.isArray(data)) break
          pages = Math.max(1, data.pages || 1)
          page += 1
        }

        if (cancelled) return

        const processed = processData({ nodes: Array.from(tickersById.values()) })
        const nodes = processed.nodes.map(row => buildHudNodeFromUniverseRow(row))
        nodeMapRef.current = {}
        nodes.forEach(n => { nodeMapRef.current[n.id] = n })
        setRawNodes(nodes)
      } catch (e) {
        console.error('Universe load error:', e)
      }
    }

    loadUniverse()

    fetch(`${API_BASE}/api/macro`)
      .then(r => r.json())
      .then(setMacroData)
      .catch(() => {})

    // F-5/A-11: Load pre-computed sector correlation matrix for sympathy links
    fetch(`${API_BASE}/api/sympathy-matrix`)
      .then(r => r.json())
      .then(data => {
        if (data?.correlation_matrix) {
          setSympathyMatrix(data.correlation_matrix)
        }
      })
      .catch(() => {})

    fetch(`${API_BASE}/api/spark?limit=8`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        const events = (data.events || data.sparks || [])
          .map(event => normalizeVelocityEvent(event, 'snapshot'))
          .filter(Boolean)
        setLiveSparks(events)
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [])

  // ── Cognitive load: 1%/s cooldown + Deep Blue ref sync ───────────────────
  useEffect(() => {
    const t = setInterval(() => setCognitiveLoad(p => Math.max(p - 1, 0)), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => { isDeepBlueRef.current = isDeepBlue }, [isDeepBlue])

  useEffect(() => () => {
    if (focusRequestTimerRef.current) clearTimeout(focusRequestTimerRef.current)
    if (focusStatusTimerRef.current) clearTimeout(focusStatusTimerRef.current)
  }, [])

  // ── Mouse tracker for X-ray overlay position ──────────────────────────────
  useEffect(() => {
    const onMove = e => {
      mousePosRef.current = { x: e.clientX, y: e.clientY }
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  // ── WebSocket live feed ───────────────────────────────────────────────────
  useEffect(() => {
    let retryTimer = null

    const connect = () => {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => setWsStatus('connected')

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload.event === 'heartbeat') return

          const nextEvent = normalizeVelocityEvent(payload, 'live')
          const ticker = nextEvent?.ticker || payload.ticker
          if (!ticker) return

          const spark = nextEvent.spark || {}
          const velocity = Number(nextEvent.total_velocity || 0)

          // Weather pulses stay in the node data, but Phase 5 removes the
          // old background weather visuals so the force graph owns the void.
          const detail = `${new Date(nextEvent.ts * 1000).toLocaleTimeString()} · ${nextEvent.headline} · ${velocity > 0 ? '+' : ''}${velocity.toFixed(1)}v`

          setRawNodes(prev => {
            const idx = prev.findIndex(n => n.id === ticker)
            if (idx === -1) return prev
            const node = prev[idx]
            node.posture = deriveNodePosture({
              posture: node.posture,
              gravity: node.gravity,
              velocityEvent: nextEvent,
            })
            const stableColor = getNodeColor({
              posture: node.posture,
              sector: node.sector,
              gravity: node.gravity,
              velocityEvent: nextEvent,
            })
            const dormantColor = dormantNodeColor({
              posture: node.posture,
              sector: node.sector,
              gravity: node.gravity,
              velocityEvent: nextEvent,
            })
            const sparkTint = pressureNodeColor({
              posture: node.posture,
              sector: node.sector,
              gravity: node.gravity,
              hasSpark: true,
              velocityEvent: nextEvent,
            })
            node.brightness   = node.gravity * (1 + Math.abs(velocity) / 10)
            node.val          = brightnessToSize(node.brightness)
            node.baseColor    = stableColor
            node.dormantColor = dormantColor
            node.pressureColor = sparkTint
            node.sparkTint    = sparkTint
            node.color        = sparkTint
            node.emissiveInt  = Math.min(Math.abs(velocity) / 18, 1.0)
            node.sparks       = spark
            node.velocityEvent = nextEvent
            node.hasSpark     = true
            node.sparkHistory = [...node.sparkHistory, detail].slice(-10)
            const mesh = node.__threeObj
            if (mesh?.material) {
              mesh.userData.sectorColor = stableColor
              mesh.userData.sparkColor = sparkTint
              mesh.userData.baseEmissive = Math.max(node.emissiveInt, mesh.userData.baseEmissive || 0.04)
              mesh.userData.hasSpark = true
              setMaterialEmissiveIntensity(mesh.material, Math.max(node.emissiveInt, 0.16))
              mesh.children?.forEach(child => {
                if (!child?.material?.color) return
                if (child.name === 'auraCore' || child.name === 'auraBloom' || child.name === 'signalRing') {
                  setMaterialColor(child.material, sparkTint)
                }
              })
            }
            nodeMapRef.current[ticker] = node
            const liveFilters = filtersRef.current
            const needsGraphReflow = node.id === selectedTickerRef.current
              || liveFilters.sparksOnly
              || Number(liveFilters.minBrightness || 0) > 0
              || Number(liveFilters.minGravity || 1) > 1
            if (!needsGraphReflow) return prev
            const next = [...prev]
            next[idx] = node
            return next
          })

          setLiveSparks(prev => upsertVelocityEvent(prev, nextEvent, 8))
          setCognitiveLoad(p => Math.min(p + 2, 100))
        } catch (e) { /* ignore */ }
      }

      ws.onclose = () => {
        setWsStatus('reconnecting')
        retryTimer = setTimeout(connect, 5000)
      }
      ws.onerror = () => ws.close()
      return ws
    }

    const ws = connect()
    return () => { clearTimeout(retryTimer); ws.close() }
  }, [])

  // ── Galaxy engine: stars + orbit + heartbeat ─────────────────────────────
  useEffect(() => {
    if (!graphRef.current) return
    const fg = graphRef.current

    // Wait for scene + camera — no THREE imports needed, just mutate existing objects
    const initGalaxy = () => {
      const scene  = fg.scene?.()
      const camera = fg.camera?.()
      const renderer = fg.renderer?.()
      if (!scene || !camera) {
        setTimeout(initGalaxy, 500)
        return
      }

      if (renderer) {
        renderer.toneMapping = THREE.ACESFilmicToneMapping
        renderer.toneMappingExposure = 1.06
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, renderProfileRef.current.pixelRatio))
      }

      camera.position.set(0, 36, 520)
      camera.lookAt(0, 0, 0)

      const controls = fg.controls?.()
      if (controls) {
        controls.target.set(0, 0, 0)
        controls.enableDamping = true
        controls.dampingFactor = 0.06
        controls.minDistance = 6
        controls.maxDistance = 9600
        controls.zoomSpeed = 1.72
        controls.update()
      }

      return

      // --- 🌌 DEEP SPACE STARFIELD START ---
      if (!scene.getObjectByName('starField')) {
        const starGeo = new THREE.BufferGeometry()
        const starCount = renderProfileRef.current.starCount
        const positions = new Float32Array(starCount * 3)
        const colors    = new Float32Array(starCount * 3)

        for (let i = 0; i < starCount * 3; i += 3) {
          const r = 800 + Math.random() * 1200
          const theta = Math.random() * 2 * Math.PI
          const phi   = Math.acos(2 * Math.random() - 1)

          positions[i]     = r * Math.sin(phi) * Math.cos(theta)
          positions[i + 1] = r * Math.sin(phi) * Math.sin(theta)
          positions[i + 2] = r * Math.cos(phi)

          const type = Math.random()
          if (type < 0.5) { colors[i]=0.6; colors[i+1]=0.8; colors[i+2]=1.0 }
          else if (type < 0.8) { colors[i]=1.0; colors[i+1]=1.0; colors[i+2]=1.0 }
          else { colors[i]=1.0; colors[i+1]=0.85; colors[i+2]=0.4 }
        }

        starGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
        starGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))

        const starMat = new THREE.PointsMaterial({
          size: 1.5,
          vertexColors: true,
          transparent: true,
          opacity: renderProfileRef.current.starOpacity,
          sizeAttenuation: true,
        })

        const starField = new THREE.Points(starGeo, starMat)
        starField.name = 'starField'
        scene.add(starField)
      }

      if (!scene.getObjectByName('marketMembrane')) {
        scene.add(buildMarketMembraneGroup())
      }
      if (!scene.getObjectByName('cognitiveStorm')) {
        scene.add(buildCognitiveStormGroup())
      }
      // --- 🌌 DEEP SPACE STARFIELD END ---

      // ── Animation loop: scene rotation + heartbeat ──────────────────────
      const animate = () => {
        animFrameRef.current = requestAnimationFrame(animate)
        const deepBlue = isDeepBlueRef.current
        const renderProfile = renderProfileRef.current
        const motionProfile = deepBlue ? FIELD_DAMPING.clockStep.deepBlue : FIELD_DAMPING.clockStep.normal
        const baseSceneRotation = deepBlue ? FIELD_DAMPING.sceneRotation.deepBlue : FIELD_DAMPING.sceneRotation.normal
        const interactionFrozen = performance.now() < interactionFreezeUntilRef.current
          || Boolean(selectedTickerRef.current)
          || targetLockRef.current.phase !== 'idle'
        const sceneRotation = interactionFrozen ? 0 : baseSceneRotation

        // Clock + rotation — calmer by default, almost glacial in Deep Blue.
        clockRef.current += motionProfile
        scene.rotation.y  += sceneRotation

        // Heartbeat pulse — less nervous energy, more latent pressure.
        const heartbeat = deepBlue ? FIELD_DAMPING.heartbeat.deep : FIELD_DAMPING.heartbeat.normal
        const pulse = heartbeat.base + heartbeat.range * Math.sin(clockRef.current * heartbeat.speed)

        displayedNodesRef.current.forEach(node => {
          const obj = node?.__threeObj
          if (!obj?.material) return
          const base = obj.userData.baseEmissive ?? 0.04
          const hasSpark = Boolean(obj.userData.hasSpark)
          const activeTargetId = selectedTickerRef.current || targetLockRef.current.ticker || ''
          const isTargeted = Boolean(activeTargetId && obj.userData.nodeId === activeTargetId)
          const dormantCol = obj.userData.dormantColor || obj.userData.sectorColor || '#1a3146'
          const sparkCol = obj.userData.pressureColor || obj.userData.sparkColor || obj.userData.sectorColor || POLARITY_FIELD_COLORS.neutral
          const targetCol = targetLockRef.current.phase === 'locked'
            ? POLARITY_FIELD_COLORS.targeted
            : blendHudColor(sparkCol, POLARITY_FIELD_COLORS.neutral, 0.2)
          const resolvedCol = isTargeted ? targetCol : hasSpark ? sparkCol : dormantCol

          // ── Depth-of-field dimming: fade non-connected nodes when locked ──
          const lockPhase = targetLockRef.current.phase
          const activeTicker = activeTargetId
          const isNeighbor = activeTicker && node.neighbors?.has(activeTicker)
          const dofDim = (lockPhase === 'locked' || lockPhase === 'settling') && !isTargeted && !isNeighbor ? 0.15 : 1

          // ── Targeted node always gets gold beacon, regardless of branch ──
          if (isTargeted) {
            const strobe = 0.5 + 0.5 * Math.sin(clockRef.current * 4.0)
            setMaterialColor(obj.material, strobe > 0.5 ? 0xffffff : 0xffd700)
            setMaterialEmissive(obj.material, 0xffd700)
            setMaterialEmissiveIntensity(obj.material, 0.8 + 2.2 * strobe)
            if (obj.material.opacity !== undefined) obj.material.opacity = 1.0
          } else if (!hasSpark && !renderProfile.animateDormantNodes) {
            if (!deepBlue) {
              setMaterialColor(obj.material, resolvedCol)
              setMaterialEmissive(obj.material, resolvedCol)
            }
            setMaterialEmissiveIntensity(obj.material, (deepBlue ? Math.min(base, 0.18) : base) * dofDim)
            if (obj.material.opacity !== undefined) obj.material.opacity = 0.9 * dofDim + 0.1
          } else if (deepBlue) {
            setMaterialColor(obj.material, 0x0055bb)
            setMaterialEmissive(obj.material, 0x0033aa)
            setMaterialEmissiveIntensity(obj.material, (Math.min(base, 0.25) + pulse) * dofDim)
          } else {
            setMaterialColor(obj.material, resolvedCol)
            setMaterialEmissive(obj.material, resolvedCol)
            setMaterialEmissiveIntensity(obj.material, (base + (hasSpark ? pulse : pulse * 0.35)) * dofDim)
            if (obj.material.opacity !== undefined) obj.material.opacity = 0.9 * dofDim + 0.1
          }

          obj.children?.forEach(child => {
            if (!child?.userData?.glowShell || !child.material) return
            const glow = child.userData.glowShell
            const phase = clockRef.current * (glow.speed || 3.4) + (glow.phase || 0)
            const opacity = (glow.baseOpacity ?? 0.08) + Math.sin(phase) * (glow.range ?? 0.03)
            child.material.opacity = Math.max(0.02, deepBlue ? opacity * 0.72 : opacity)
            if (!deepBlue && (child.name === 'auraCore' || child.name === 'auraBloom' || child.name === 'signalRing')) {
              setMaterialColor(child.material, resolvedCol)
            }
            const scaleBase = glow.scaleBase ?? 1
            const scaleRange = glow.scaleRange ?? 0.04
            const scale = scaleBase + Math.sin(phase) * scaleRange
            child.scale.setScalar(Math.max(0.85, scale))
          })

          // Targeted node beacon — force minimum size + pulse so it's unmissable
          if (isTargeted) {
            const baseVal = Number(node.val || 2)
            const minScale = baseVal < 5 ? 5 / Math.max(0.5, baseVal) : 1.2
            const breathe = (minScale * 1.2) + (minScale * 0.4) * Math.sin(clockRef.current * 4.0)
            obj.scale.setScalar(breathe)

            // Add/update beacon ring — bright gold, large, unmissable
            let ring = obj.getObjectByName('targetBeaconRing')
            if (!ring) {
              const ringGeo = new THREE.RingGeometry(2.5, 3.5, 48)
              const ringMat = new THREE.MeshBasicMaterial({
                color: 0xffd700,
                transparent: true,
                opacity: 0.95,
                side: THREE.DoubleSide,
                blending: THREE.AdditiveBlending,
                depthWrite: false,
              })
              ring = new THREE.Mesh(ringGeo, ringMat)
              ring.name = 'targetBeaconRing'
              obj.add(ring)
            }
            const ringPulse = 0.5 + 0.5 * Math.sin(clockRef.current * 4.0)
            ring.material.opacity = 0.5 + 0.5 * ringPulse
            ring.scale.setScalar(1.2 + 0.5 * ringPulse)
            // Billboard: face camera by extracting camera from graphRef
            const cam = graphRef.current?.camera?.()
            if (cam) ring.lookAt(cam.position)
          } else {
            // Remove ring if target released
            const oldRing = obj.getObjectByName('targetBeaconRing')
            if (oldRing) { oldRing.geometry?.dispose(); oldRing.material?.dispose(); obj.remove(oldRing) }
            if (obj.scale.x !== 1) obj.scale.setScalar(1)
          }

          const spinRate = obj.userData.spinRate || 0
          if (spinRate > 0) {
            obj.rotation.y += spinRate
            obj.rotation.x += spinRate * 0.42
          }
        })

        // ── World-space lock pillar: always-visible locator through selected node ──
        // Solves "where is my selected node" when zoomed out or when filters hide the node.
        {
          const pinned = pinnedNodeRef.current
          const activeTargetId = selectedTickerRef.current || targetLockRef.current.ticker || ''
          const shouldShow = Boolean(activeTargetId) && pinned && Number.isFinite(pinned.x) && Number.isFinite(pinned.y)
          if (shouldShow) {
            let pillar = lockPillarRef.current
            if (!pillar) {
              const pillarGroup = new THREE.Group()
              pillarGroup.name = 'lockPillar'
              // Tall thin cylinder — bright gold, additive blending so it glows through other geometry
              const beamGeo = new THREE.CylinderGeometry(0.6, 0.6, 2400, 12, 1, true)
              const beamMat = new THREE.MeshBasicMaterial({
                color: 0xffd700,
                transparent: true,
                opacity: 0.55,
                side: THREE.DoubleSide,
                blending: THREE.AdditiveBlending,
                depthWrite: false,
              })
              const beam = new THREE.Mesh(beamGeo, beamMat)
              beam.name = 'lockPillarBeam'
              pillarGroup.add(beam)
              // Large camera-facing halo ring at node altitude, screen-space sized in RAF
              const haloGeo = new THREE.RingGeometry(8, 9, 64)
              const haloMat = new THREE.MeshBasicMaterial({
                color: 0xffd700,
                transparent: true,
                opacity: 0.85,
                side: THREE.DoubleSide,
                blending: THREE.AdditiveBlending,
                depthWrite: false,
              })
              const halo = new THREE.Mesh(haloGeo, haloMat)
              halo.name = 'lockPillarHalo'
              pillarGroup.add(halo)
              scene.add(pillarGroup)
              lockPillarRef.current = pillarGroup
              pillar = pillarGroup
            }
            // Position pillar at pinned-node world coordinates
            pillar.position.set(pinned.x, pinned.y, pinned.z || 0)
            // Gentle pulse for the beam
            const beamPulse = 0.45 + 0.25 * Math.sin(clockRef.current * 2.6)
            const beam = pillar.getObjectByName('lockPillarBeam')
            if (beam?.material) beam.material.opacity = beamPulse
            // Halo: scale based on camera distance so it's always visually ~constant size
            const halo = pillar.getObjectByName('lockPillarHalo')
            const cam = graphRef.current?.camera?.()
            if (halo && cam) {
              const distToCam = cam.position.distanceTo(pillar.position)
              const targetRadius = Math.max(1, distToCam * 0.04)  // 4% of distance → ~4% of view
              halo.scale.setScalar(targetRadius)
              halo.lookAt(cam.position)
              const haloPulse = 0.6 + 0.4 * Math.sin(clockRef.current * 3.4)
              if (halo.material) halo.material.opacity = 0.55 + 0.35 * haloPulse
            }
          } else if (lockPillarRef.current) {
            scene.remove(lockPillarRef.current)
            lockPillarRef.current.traverse?.(o => { o.geometry?.dispose?.(); o.material?.dispose?.() })
            lockPillarRef.current = null
          }
        }

        const starField = scene.getObjectByName('starField')
        if (starField?.material) {
          const targetOp = deepBlue ? 0.18 : renderProfile.starOpacity
          starField.material.opacity += (targetOp - starField.material.opacity) * 0.05
        }

        const membrane = scene.getObjectByName('marketMembrane')
        if (membrane) {
          const pulseState = marketPulseRef.current || { bias: 'balanced', intensity: 0.2, positive: 0, negative: 0 }
          const polarityTilt = pulseState.bias === 'bullish' ? 0.00014 : pulseState.bias === 'bearish' ? -0.00014 : 0
          membrane.rotation.y += (baseSceneRotation * 1.5) + 0.00016 + polarityTilt
          membrane.rotation.x = Math.sin(clockRef.current * 0.13) * 0.06
          membrane.rotation.z = Math.cos(clockRef.current * 0.11) * 0.035

          const membraneScale = 0.988 + pulse * 0.28 + (pulseState.intensity || 0) * 0.02
          membrane.scale.setScalar(membraneScale)

          const outer = membrane.getObjectByName('membraneOuter')
          const inner = membrane.getObjectByName('membraneInner')
          const pulseShell = membrane.getObjectByName('membranePulse')
          const lattice = membrane.getObjectByName('membraneLattice')
          const equator = membrane.getObjectByName('membraneEquator')
          const accent = pulseState.bias === 'bearish'
            ? POLARITY_FIELD_COLORS.bearish
            : pulseState.bias === 'bullish'
              ? POLARITY_FIELD_COLORS.bullish
              : POLARITY_FIELD_COLORS.neutral

          if (outer?.material) {
            outer.material.opacity = (outer.userData.baseOpacity || 0.11) + pulse * 0.24 + (pulseState.intensity || 0) * 0.02
            setMaterialColor(outer.material, accent)
          }
          if (inner?.material) {
            inner.material.opacity = (inner.userData.baseOpacity || 0.09) + pulse * 0.18
          }
          if (pulseShell?.material) {
            pulseShell.material.opacity = (pulseShell.userData.baseOpacity || 0.14) + pulse * 0.3 + (pulseState.intensity || 0) * 0.03
            setMaterialColor(pulseShell.material, pulseState.bias === 'quiet' ? POLARITY_FIELD_COLORS.targeted : accent)
            pulseShell.rotation.y -= 0.0009
            pulseShell.rotation.x += 0.00035
          }
          if (lattice) {
            lattice.rotation.y -= 0.00022
            lattice.children.forEach((segment, index) => {
              if (!segment.material) return
              segment.material.opacity = Math.max(
                0.018,
                (segment.userData.latticeOpacity || 0.06) + Math.sin(clockRef.current * (0.52 + index * 0.03) + index) * 0.014,
              )
            })
          }
          if (equator?.material) {
            equator.material.opacity = 0.08 + pulse * 0.2 + (pulseState.total > 0 ? 0.02 : 0)
            setMaterialColor(equator.material, pulseState.bias === 'quiet' ? POLARITY_FIELD_COLORS.targeted : accent)
          }
        }

        const storm = scene.getObjectByName('cognitiveStorm')
        if (storm) {
          const pulseState = marketPulseRef.current || { bias: 'balanced', intensity: 0.2 }
          const loadRatio = Math.max(0, Math.min(1, cognitiveLoad / 100))
          const stormAccent = pulseState.bias === 'bearish'
            ? new THREE.Color('#ff7d96')
            : pulseState.bias === 'bullish'
              ? new THREE.Color('#89ffd3')
              : new THREE.Color('#8ce8ff')
          const stormSecondary = new THREE.Color('#b99cff')
          storm.rotation.z += 0.0018 + loadRatio * 0.0024
          storm.rotation.y -= 0.001 + (pulseState.intensity || 0) * 0.0012
          storm.rotation.x = Math.sin(clockRef.current * 0.34) * 0.24
          const stormScale = 0.92 + loadRatio * 0.44 + pulse * 0.6
          storm.scale.setScalar(stormScale)

          const armMaterials = storm.userData.armMaterials || []
          armMaterials.forEach((material, index) => {
            const mixed = stormAccent.clone().lerp(stormSecondary, index % 2 === 0 ? 0.24 : 0.66)
            material.color.copy(mixed)
            material.opacity = 0.12 + loadRatio * 0.2 + Math.sin(clockRef.current * (1.2 + index * 0.08)) * 0.02
          })

          const cloudMaterial = storm.userData.cloudMaterial
          if (cloudMaterial) {
            cloudMaterial.opacity = 0.14 + loadRatio * 0.22 + (pulseState.intensity || 0) * 0.06
            cloudMaterial.color.copy(stormAccent)
          }
          const haloMaterial = storm.userData.haloMaterial
          if (haloMaterial) {
            haloMaterial.color.copy(stormAccent.clone().lerp(stormSecondary, 0.4))
            haloMaterial.opacity = 0.1 + loadRatio * 0.16
          }
          const coreMaterial = storm.userData.coreMaterial
          if (coreMaterial) {
            coreMaterial.opacity = 0.84 + loadRatio * 0.08
          }
        }

        // Weather tether decay — fades to zero over ~4 minutes (0.0003/frame @ 60fps)
        if (weatherLinesRef.current) {
          weatherDecayRef.current = Math.max(0, weatherDecayRef.current - 0.0003)
          const op = weatherDecayRef.current
          weatherLinesRef.current.traverse(obj => {
            if (!obj.material) return
            const weatherGlow = obj.userData?.weatherGlow
            if (weatherGlow) {
              const phase = clockRef.current * (weatherGlow.speed || 4.2) + (weatherGlow.phase || 0)
              const pulseOpacity = (weatherGlow.baseOpacity ?? 0.2) + Math.sin(phase) * (weatherGlow.range ?? 0.06)
              obj.material.opacity = Math.max(0, op * Math.max(0.04, pulseOpacity))
              return
            }
            if ('opacity' in obj.material) {
              obj.material.opacity = op
            }
          })
          if (op <= 0) {
            scene.remove(weatherLinesRef.current)
            weatherLinesRef.current = null
          }
        }

        // Target node ref (crosshair purged — DoF traversal only)
        const tNode = targetNodeRef.current

        // ── Competitor Orbit Physics ──────────────────────────────────────────
        if (orbitingPeersRef.current.length > 0 && tNode) {
          const cx = tNode.x || 0
          const cy = tNode.y || 0
          const cz = tNode.z || 0
          const orbitMotionScale = targetLockRef.current.phase === 'idle'
            ? (interactionFrozen ? 0.24 : 1)
            : 0.12
          const orbitSpeed = clockRef.current * (deepBlue ? FIELD_DAMPING.peerOrbit.deepBlue : FIELD_DAMPING.peerOrbit.normal) * orbitMotionScale

          orbitingPeersRef.current.forEach(peer => {
            peer.node.x = cx + Math.cos(orbitSpeed + peer.angleOffset) * peer.radius
            peer.node.z = cz + Math.sin(orbitSpeed + peer.angleOffset) * peer.radius
            peer.node.y = cy + Math.sin(orbitSpeed * 2 + peer.angleOffset) * FIELD_DAMPING.peerOrbit.lift

            // Brighten peer mesh directly via Three.js object (React state won't reach it)
            const obj = peer.node.__threeObj
            if (obj?.material) {
              setMaterialEmissiveIntensity(obj.material, deepBlue ? 0.25 : 0.72)
              if (!deepBlue) {
                const col = peer.node.userData?.sectorColor || peer.node.color || '#00d4ff'
                setMaterialColor(obj.material, col)
                setMaterialEmissive(obj.material, col)
              }
            }

            // Gravity rings purged — no ring drag needed
          })
        }

        // ── Gamma Well Physics ────────────────────────────────────────────────
        if (gammaWellsRef.current.length > 0 && tNode) {
          const wd = gammaWellsRef.current[0]
          const churn = clockRef.current * (deepBlue ? 1.5 : 4.0)
          wd.mesh.rotation.y = churn
          wd.mesh.rotation.z = churn * 0.5
          wd.mesh.material.emissiveIntensity = 0.65 + Math.sin(clockRef.current * 5) * 0.15
          // Well follows target node and bobs with magnetic drag
          const wellR = wd.mesh.geometry.parameters?.radius || 30
          const drag  = Math.sin(clockRef.current * 3) * (wd.pullStrength * 8)
          wd.mesh.position.set(tNode.x||0, (tNode.y||0) - wellR - 20 - drag, tNode.z||0)
        }

        bloomImpulseRef.current = Math.max(0, bloomImpulseRef.current * (deepBlue ? 0.88 : 0.91) - (deepBlue ? 0.01 : 0.006))
      }
      animate()
    }

    setTimeout(initGalaxy, 1200)

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      const camera = fg.camera?.()
      if (camera?.view) {
        camera.clearViewOffset()
        camera.updateProjectionMatrix()
      }
    }
  }, [rawNodes.length > 0])   // fire once nodes are loaded

  const selectedNode = useMemo(() => {
    if (!selectedTicker) return null
    return nodeMapRef.current[selectedTicker] || rawNodes.find(n => n.id === selectedTicker) || null
  }, [rawNodes, selectedTicker])

  useEffect(() => {
    settledTargetRef.current = ''
  }, [selectedTicker])

  // ── Target node tracking (crosshair purged — pure DoF traversal) ─────────
  useEffect(() => {
    const scene = graphRef.current?.scene?.()
    if (scene) {
      const old = scene.getObjectByName('targetMarker')
      if (old) scene.remove(old)
    }
    targetMarkerRef.current = null
    targetNodeRef.current = null
    if (!selectedNode) return
    targetNodeRef.current = nodeMapRef.current[selectedNode.id] || selectedNode
  }, [selectedNode])

  // ── Weather tether lines: build on each new shock event ──────────────────
  useEffect(() => {
    if (!weatherTrigger) return
    const scene = graphRef.current?.scene?.()
    if (!scene) return

    const old = scene.getObjectByName('weatherTethers')
    if (old) scene.remove(old)

    const disrupted = []
    const recovery = []
    for (const node of Object.values(nodeMapRef.current)) {
      const weatherValue = node.sparks?.weather
      if (!weatherValue || node.x == null) continue
      if (weatherValue < 0) disrupted.push(node)
      else recovery.push(node)
    }

    if (disrupted.length === 0 && recovery.length === 0) return

    const sourceNodes = disrupted.length > 0 ? disrupted.slice(0, 30) : recovery.slice(0, 12)
    const cx = sourceNodes.reduce((sum, node) => sum + (node.x || 0), 0) / sourceNodes.length
    const cy = sourceNodes.reduce((sum, node) => sum + (node.y || 0), 0) / sourceNodes.length
    const cz = sourceNodes.reduce((sum, node) => sum + (node.z || 0), 0) / sourceNodes.length

    const group = new THREE.Group()
    group.name = 'weatherTethers'

    const stormCoreColor = disrupted.length > 0 ? 0xff7a7a : 0x51f2c6
    const stormCore = new THREE.Mesh(
      new THREE.SphereGeometry(disrupted.length > 0 ? 7 : 5, 18, 18),
      new THREE.MeshBasicMaterial({
        color: stormCoreColor,
        transparent: true,
        opacity: disrupted.length > 0 ? 0.18 : 0.12,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    stormCore.position.set(cx, cy, cz)
    stormCore.userData.weatherGlow = {
      baseOpacity: disrupted.length > 0 ? 0.18 : 0.12,
      range: disrupted.length > 0 ? 0.08 : 0.05,
      speed: disrupted.length > 0 ? 5.6 : 3.4,
      phase: 0,
    }
    group.add(stormCore)

    for (const node of disrupted.slice(0, 26)) {
      const points = makeJaggedLine(
        { x: cx, y: cy, z: cz },
        { x: node.x, y: node.y, z: node.z || 0 },
        12,
        16,
      )
      const stroke = buildWeatherStroke(points, 0xff5454, {
        radius: 1.2,
        shellOpacity: 0.24,
        shellRange: 0.1,
        coreOpacity: 0.88,
        coreRange: 0.14,
        flareRadius: 2.8,
        flareOpacity: 0.38,
        speed: 5.4,
      })
      group.add(stroke)
    }

    for (const node of recovery.slice(0, 12)) {
      const points = makeArcedLine(
        { x: cx, y: cy, z: cz },
        { x: node.x, y: node.y, z: node.z || 0 },
        70,
        28,
      )
      const stroke = buildWeatherStroke(points, 0x1fe0a5, {
        radius: 0.78,
        shellOpacity: 0.16,
        shellRange: 0.07,
        coreOpacity: 0.68,
        coreRange: 0.08,
        flareRadius: 2.0,
        flareOpacity: 0.26,
        speed: 3.6,
      })
      group.add(stroke)
    }

    scene.add(group)
    weatherLinesRef.current = group
    weatherDecayRef.current = 1.0
  }, [weatherTrigger])

  // ── Filter engine ─────────────────────────────────────────────────────────
  const filteredNodes = useMemo(() => {
    // Force-include selected + locked tickers so user-targeted nodes are NEVER hidden by filters.
    // This prevents the "blue pointer in empty space" bug where NodeInspector shows data
    // but the 3D mesh was filtered out by sector/brightness/sparks.
    const forceIds = new Set()
    if (selectedTicker) forceIds.add(selectedTicker)
    if (targetLock.ticker) forceIds.add(targetLock.ticker)
    return rawNodes.filter(n => {
      if (forceIds.has(n.id)) return true
      if (filters.sector !== 'ALL' && n.sector !== filters.sector) return false
      if (n.gravity < filters.minGravity) return false
      if (n.brightness < filters.minBrightness) return false
      if (filters.sparksOnly && !n.hasSpark) return false
      return true
    })
  }, [rawNodes, filters, selectedTicker, targetLock.ticker])

  const activeSparkNodeCount = useMemo(
    () => filteredNodes.reduce((count, node) => count + (node.hasSpark ? 1 : 0), 0),
    [filteredNodes],
  )

  const renderProfile = useMemo(() => {
    if (filteredNodes.length > 5200) return HUD_RENDER_PROFILES.dense
    if (filteredNodes.length > 1400 || activeSparkNodeCount > 18) return HUD_RENDER_PROFILES.balanced
    return HUD_RENDER_PROFILES.cinematic
  }, [activeSparkNodeCount, filteredNodes.length])

  const displayedNodes = useMemo(() => {
    let budget = renderProfile.visibleNodeBudget
    if (renderProfile.name === 'dense' && activeSparkNodeCount === 0) {
      if (!selectedTicker && !targetLock.ticker) {
        budget = Math.min(budget, 480)
      } else {
        budget = Math.min(budget, 640)
      }
    }
    if (!Number.isFinite(budget) || filteredNodes.length <= budget) return filteredNodes

    const byId = new Map(filteredNodes.map(node => [node.id, node]))
    const selected = selectedTicker ? byId.get(selectedTicker) : null
    const targetTicker = targetLock.ticker || ''
    const locked = targetTicker ? byId.get(targetTicker) : null
    const focusNode = selected || locked || null
    const focusSector = focusNode?.sector || ''
    const sorted = [...filteredNodes].sort(
      (a, b) => nodePriorityScore(b, {
        selectedTicker,
        targetTicker,
        hoverTicker: '',
        focusSector,
      }) - nodePriorityScore(a, {
        selectedTicker,
        targetTicker,
        hoverTicker: '',
        focusSector,
      }),
    )

    const picked = []
    const seen = new Set()
    const pushNode = (node) => {
      if (!node?.id || seen.has(node.id) || picked.length >= budget) return
      seen.add(node.id)
      picked.push(node)
    }

    ;[selected, locked].forEach(pushNode)

    if (focusSector) {
      sorted
        .filter(node => node.sector === focusSector)
        .slice(0, Math.min(220, Math.floor(budget * 0.18)))
        .forEach(pushNode)
    }

    const sectorBuckets = new Map()
    sorted.forEach(node => {
      const key = node.sector || 'unknown'
      const bucket = sectorBuckets.get(key) || []
      bucket.push(node)
      sectorBuckets.set(key, bucket)
    })
    const sectorFloor = Math.max(10, Math.floor(budget / Math.max(1, sectorBuckets.size) / 2.4))
    sectorBuckets.forEach(bucket => bucket.slice(0, sectorFloor).forEach(pushNode))

    sorted
      .filter(node => node.hasSpark)
      .slice(0, Math.min(280, Math.floor(budget * 0.22)))
      .forEach(pushNode)

    sorted.forEach(pushNode)
    return picked
  }, [activeSparkNodeCount, filteredNodes, renderProfile.name, renderProfile.visibleNodeBudget, selectedTicker, targetLock.ticker])

  const denseShellPositions = useMemo(() => null, [displayedNodes])

  const richVisualNodeIds = useMemo(() => {
    if (!Number.isFinite(renderProfile.richNodeBudget)) return null
    return new Set(
      [...displayedNodes]
        .sort((a, b) => {
          const sparkDelta = Number(Boolean(b.hasSpark)) - Number(Boolean(a.hasSpark))
          if (sparkDelta) return sparkDelta
          const brightDelta = Number(b.brightness || 0) - Number(a.brightness || 0)
          if (brightDelta) return brightDelta
          return Number(b.gravity || 0) - Number(a.gravity || 0)
        })
        .slice(0, renderProfile.richNodeBudget)
        .map(node => node.id),
    )
  }, [displayedNodes, renderProfile.richNodeBudget])

  useEffect(() => {
    renderProfileRef.current = renderProfile
    const renderer = graphRef.current?.renderer?.()
    if (renderer) {
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, renderProfile.pixelRatio))
    }
  }, [renderProfile])

  useEffect(() => {
    displayedNodesRef.current = displayedNodes
  }, [displayedNodes])

  useEffect(() => {
    const nextFixed = new Set()
    if (renderProfile.name === 'dense' && denseShellPositions) {
      displayedNodes.forEach(node => {
        const pos = denseShellPositions.get(node.id)
        if (!pos) return
        node.x = pos.x
        node.y = pos.y
        node.z = pos.z
        node.fx = pos.x
        node.fy = pos.y
        node.fz = pos.z
        nextFixed.add(node.id)
      })
    }

    rawNodes.forEach(node => {
      if (!node?.id) return
      if (nextFixed.has(node.id)) return
      if (denseFixedNodeIdsRef.current.has(node.id)) {
        node.fx = undefined
        node.fy = undefined
        node.fz = undefined
      }
    })

    denseFixedNodeIdsRef.current = nextFixed
  }, [denseShellPositions, displayedNodes, rawNodes, renderProfile.name])

  const graphData = useMemo(() => {
    const links = []
    const recentBySector = {}
    const activeBySector = {}
    const seenPairs = new Set()
    const sympathyLeadByNode = {}
    const adjacencyDepth = renderProfile.structuralAdjacencyDepth ?? 2

    const pushSectorLink = (sourceNode, targetNode, reason = 'adjacency', meta = {}) => {
      if (!sourceNode?.id || !targetNode?.id || sourceNode.id === targetNode.id) return
      const key = [sourceNode.id, targetNode.id].sort().join('::')
      if (seenPairs.has(key)) return
      seenPairs.add(key)
      links.push({
        linkKey: `${sourceNode.id}->${targetNode.id}:${reason}`,
        source: sourceNode.id,
        target: targetNode.id,
        sympathyStrength: sympathyStrengthBetween(sourceNode, targetNode),
        sympathyPolarity: sympathyPolarityBetween(sourceNode, targetNode),
        kind: reason,
        reason,
        ...meta,
      })
    }

    displayedNodes.forEach(node => {
      if (!node.sector) return
      if (!recentBySector[node.sector]) recentBySector[node.sector] = []
      if (!activeBySector[node.sector]) activeBySector[node.sector] = []

      if (adjacencyDepth > 0) {
        recentBySector[node.sector].forEach(prevNode => {
          pushSectorLink(node, prevNode, 'adjacency')
        })
      }

      recentBySector[node.sector].push(node)
      if (recentBySector[node.sector].length > adjacencyDepth) {
        recentBySector[node.sector].shift()
      }

      if (node.hasSpark && Math.abs(velocityValue(node)) >= 1.5) {
        activeBySector[node.sector].push(node)
      }
    })

    Object.values(activeBySector).forEach(nodes => {
      if (nodes.length < 2) return
      const ranked = [...nodes].sort((a, b) => Math.abs(velocityValue(b)) - Math.abs(velocityValue(a)))
      const leader = ranked[0]
      const followers = ranked.slice(1, 4)
      if (followers.length) {
        sympathyLeadByNode[leader.id] = {
          role: 'leader',
          leader: leader.id,
          sector: leader.sector || '',
          followers: followers.map(peer => peer.id),
          label: `SYMPATHY: ${formatSectorLabel(leader.sector)}`,
        }
      }
      followers.forEach((peer, lane) => {
        const strength = sympathyStrengthBetween(leader, peer)
        const polarity = sympathyPolarityBetween(leader, peer)
        sympathyLeadByNode[peer.id] = {
          role: 'follower',
          leader: leader.id,
          sector: leader.sector || peer.sector || '',
          strength,
          polarity,
          label: `SYMPATHY: ${formatSectorLabel(leader.sector || peer.sector)}`,
        }
        pushSectorLink(leader, peer, 'sympathy_bleed', {
          sympathyLeader: leader.id,
          sympathyPeer: peer.id,
          sympathySector: leader.sector || peer.sector || '',
          sympathyLane: lane,
          sympathyLabel: `SYMPATHY: ${formatSectorLabel(leader.sector || peer.sector)}`,
        })
      })
    })

    // ── Build neighbor map for DoF traversal ──────────────────────────────
    const neighborMap = {}
    displayedNodes.forEach(node => { neighborMap[node.id] = new Set() })
    links.forEach(link => {
      const sId = typeof link.source === 'object' ? link.source?.id : link.source
      const tId = typeof link.target === 'object' ? link.target?.id : link.target
      if (sId && tId && neighborMap[sId] && neighborMap[tId]) {
        neighborMap[sId].add(tId)
        neighborMap[tId].add(sId)
      }
    })
    displayedNodes.forEach(node => { node.neighbors = neighborMap[node.id] || new Set() })

    return { nodes: displayedNodes, links, sympathyLeadByNode, neighborMap }
  }, [displayedNodes, renderProfile.structuralAdjacencyDepth])

  const sympathyLinks = useMemo(() => (
    graphData.links.filter(
      link => link?.kind === 'sympathy_bleed' && (link?.sympathyStrength || 0) >= FIELD_DAMPING.link.sympathyActivation,
    )
  ), [graphData.links])

  const sympathyDensityPolicy = useMemo(() => {
    const sectorSummary = {}
    sympathyLinks.forEach(link => {
      const sector = link?.sympathySector || 'unknown'
      const entry = sectorSummary[sector] || {
        count: 0,
        dominantKey: '',
        dominantStrength: -1,
      }
      entry.count += 1
      if ((link?.sympathyStrength || 0) > entry.dominantStrength) {
        entry.dominantStrength = Number(link?.sympathyStrength || 0)
        entry.dominantKey = link?.linkKey || ''
      }
      sectorSummary[sector] = entry
    })

    const total = sympathyLinks.length
    let mode = 'full'
    if (filters.sympathyShield) {
      const highestSectorCount = Math.max(0, ...Object.values(sectorSummary).map(entry => entry.count))
      if (filteredNodes.length > 800 || total > 18) mode = 'suppressed'
      else if (filteredNodes.length > 250 || total > 8 || highestSectorCount > 1) mode = 'grouped'
    }

    const groupedKeys = new Set(
      Object.values(sectorSummary)
        .map(entry => entry.dominantKey)
        .filter(Boolean),
    )

    return {
      enabled: Boolean(filters.sympathyShield),
      total,
      mode,
      sectorSummary,
      groupedKeys,
    }
  }, [filters.sympathyShield, sympathyLinks])

  const sectors = useMemo(() => {
    const s = new Set(rawNodes.map(n => n.sector).filter(Boolean))
    return [...s].sort()
  }, [rawNodes])

  const linkVisibility = useCallback((link) => {
    const source = typeof link?.source === 'object' ? link.source : nodeMapRef.current[link?.source]
    const target = typeof link?.target === 'object' ? link.target : nodeMapRef.current[link?.target]
    if (!source || !target) return false

    const sourceId = source?.id || source?.ticker || ''
    const targetId = target?.id || target?.ticker || ''
    const hoverTicker = hoverData?.node?.id || ''
    const focusTicker = selectedTicker || targetLock.ticker || hoverTicker
    const focusSector = (focusTicker && nodeMapRef.current[focusTicker]?.sector) || ''
    const touchesSelection = Boolean(selectedTicker && (sourceId === selectedTicker || targetId === selectedTicker))
    const touchesHover = Boolean(hoverTicker && (sourceId === hoverTicker || targetId === hoverTicker))
    const touchesTarget = Boolean(targetLock.ticker && (sourceId === targetLock.ticker || targetId === targetLock.ticker))

    if (touchesSelection || touchesHover || touchesTarget) return true
    if (renderProfile.name !== 'dense') return true

    if (link?.kind === 'sympathy_bleed') {
      if ((link?.sympathyStrength || 0) < FIELD_DAMPING.link.sympathyActivation) return false
      if (sympathyDensityPolicy.mode === 'suppressed') return false
      if (sympathyDensityPolicy.mode === 'grouped') {
        return sympathyDensityPolicy.groupedKeys.has(link?.linkKey || '')
      }
      return true
    }

    if (source?.hasSpark || target?.hasSpark) return true
    if (focusSector && source?.sector === focusSector && target?.sector === focusSector) return true
    return false
  }, [hoverData?.node?.id, renderProfile.name, selectedTicker, sympathyDensityPolicy.groupedKeys, sympathyDensityPolicy.mode, targetLock.ticker])

  // ── Neighbor-aware link coloring for DoF traversal ──────────────────────
  const neighborLinkColor = useCallback((link) => {
    const focusTicker = selectedTicker || targetLock.ticker || ''
    if (!focusTicker) {
      // No active node — use sector-based coloring
      const rawSector = String(
        link?.sector || link?.sympathySector
        || (typeof link?.source === 'object' ? link?.source?.sector : '')
        || (typeof link?.target === 'object' ? link?.target?.sector : '')
        || '',
      ).trim().toLowerCase()
      const sectorMap = {
        technology: 'rgba(56, 189, 248, 0.3)', tech: 'rgba(56, 189, 248, 0.3)', semis: 'rgba(56, 189, 248, 0.3)',
        healthcare: 'rgba(167, 139, 250, 0.3)', biotech: 'rgba(167, 139, 250, 0.3)',
        energy: 'rgba(250, 204, 21, 0.3)',
        financials: 'rgba(52, 211, 153, 0.3)',
        'consumer cyclical': 'rgba(244, 114, 182, 0.3)', consumer: 'rgba(244, 114, 182, 0.3)',
      }
      return sectorMap[rawSector] || 'rgba(255, 255, 255, 0.05)'
    }
    // Active node — illuminate only connected links
    const sourceId = typeof link?.source === 'object' ? link.source?.id : link?.source
    const targetId = typeof link?.target === 'object' ? link.target?.id : link?.target
    const isConnected = sourceId === focusTicker || targetId === focusTicker
    return isConnected ? 'rgba(114, 229, 255, 0.85)' : 'rgba(255, 255, 255, 0.02)'
  }, [selectedTicker, targetLock.ticker])

  // ── Neighbor-aware link width: thicken connected links when node is focused ──
  const neighborLinkWidth = useCallback((link) => {
    const focusTicker = selectedTicker || targetLock.ticker || ''
    if (!focusTicker) return 0.5
    const sourceId = typeof link?.source === 'object' ? link.source?.id : link?.source
    const targetId = typeof link?.target === 'object' ? link.target?.id : link?.target
    const isConnected = sourceId === focusTicker || targetId === focusTicker
    return isConnected ? 1.8 : 0.3
  }, [selectedTicker, targetLock.ticker])

  const linkFocusState = useCallback((link) => {
    const source = typeof link?.source === 'object' ? link.source : nodeMapRef.current[link?.source]
    const target = typeof link?.target === 'object' ? link.target : nodeMapRef.current[link?.target]
    const focusTicker = selectedTicker || targetLock.ticker || hoverData?.node?.id || ''
    if (!focusTicker) {
      return { focused: false, source, target }
    }
    const sourceId = source?.id || source?.ticker || ''
    const targetId = target?.id || target?.ticker || ''
    return {
      focused: sourceId === focusTicker || targetId === focusTicker,
      source,
      target,
    }
  }, [hoverData?.node?.id, selectedTicker, targetLock.ticker])

  const findMagnetNodeAtPointer = useCallback((clientX, clientY) => {
    const camera = graphRef.current?.camera?.()
    const renderer = graphRef.current?.renderer?.()
    const dom = renderer?.domElement
    if (!camera || !dom) return null

    const rect = dom.getBoundingClientRect()
    const pointerX = Number.isFinite(clientX) ? clientX : mousePosRef.current.x
    const pointerY = Number.isFinite(clientY) ? clientY : mousePosRef.current.y
    if (pointerX < rect.left || pointerX > rect.right || pointerY < rect.top || pointerY > rect.bottom) return null

    const width = Math.max(1, rect.width)
    const height = Math.max(1, rect.height)
    const safeLeft = rect.left + INTERACTION_ASSIST.sceneSafeInsets.left
    const safeRight = rect.right - INTERACTION_ASSIST.sceneSafeInsets.right
    const safeTop = rect.top + INTERACTION_ASSIST.sceneSafeInsets.top
    const safeBottom = rect.bottom - INTERACTION_ASSIST.sceneSafeInsets.bottom
    const baseThreshold = INTERACTION_ASSIST.directMagnetPx[renderProfile.name] || INTERACTION_ASSIST.directMagnetPx.balanced

    let bestNode = null
    let bestScore = Number.POSITIVE_INFINITY

    displayedNodesRef.current.forEach(node => {
      if (!node || node.x == null || node.y == null) return

      const projected = new THREE.Vector3(node.x || 0, node.y || 0, node.z || 0).project(camera)
      if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y) || projected.z > 1.1) return

      const screenX = rect.left + ((projected.x + 1) * 0.5) * width
      const screenY = rect.top + ((1 - projected.y) * 0.5) * height
      if (screenX < safeLeft || screenX > safeRight || screenY < safeTop || screenY > safeBottom) return

      const distance = Math.hypot(screenX - pointerX, screenY - pointerY)
      const projectedRadius = Math.max(8, (node.val || 2) * (renderProfile.name === 'dense' ? 2.8 : 2.2))
      const threshold = baseThreshold + projectedRadius
      if (distance > threshold) return

      const hoverBoost = hoverData?.node?.id === node.id ? 12 : 0
      const sparkBoost = node.hasSpark ? 6 : 0
      const gravityBoost = Math.min(6, Number(node.gravity || 0) * 0.08)
      const score = distance - hoverBoost - sparkBoost - gravityBoost

      if (score < bestScore) {
        bestScore = score
        bestNode = node
      }
    })

    return bestNode
  }, [hoverData?.node?.id, renderProfile.name])

  const focusCameraToTicker = useCallback((ticker, mode = 'click', attempt = 0) => {
    const liveNode = nodeMapRef.current[ticker] || rawNodes.find(n => n.id === ticker)
    if (!graphRef.current || !liveNode) {
      // Node does not yet exist in the graph (still loading, or filtered out upstream).
      // Retry for up to ~2s, then surface a visible status instead of silently giving up.
      if (attempt >= 20) {
        try { flashFocusStatus(`${ticker} not found in current universe`, 'error') } catch (_) {}
        return
      }
      if (focusRequestTimerRef.current) clearTimeout(focusRequestTimerRef.current)
      focusRequestTimerRef.current = setTimeout(() => focusCameraToTicker(ticker, mode, attempt + 1), 100)
      return
    }
    if (liveNode.x == null || liveNode.y == null) {
      // Node exists but simulation has not placed it yet (waiting for d3 tick).
      // Extend retry budget from 6×90ms (540ms) to 20×100ms (2s) and emit visible error on timeout.
      if (attempt >= 20) {
        try { flashFocusStatus(`${ticker} position pending — simulation still warming`, 'error') } catch (_) {}
        return
      }
      if (focusRequestTimerRef.current) clearTimeout(focusRequestTimerRef.current)
      focusRequestTimerRef.current = setTimeout(() => focusCameraToTicker(ticker, mode, attempt + 1), 100)
      return
    }

    // ── Cancel any in-flight camera animation ──
    if (cameraFlightRef.current?.id) {
      cancelAnimationFrame(cameraFlightRef.current.id)
      cameraFlightRef.current = null
    }

    const camera = graphRef.current?.camera?.()
    if (!camera) return

    // ── Easing: easeInOutCubic ──
    const easeInOutCubic = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2

    // ── Compute approach vector (keep existing camera angle, just close distance) ──
    const nodePos = new THREE.Vector3(liveNode.x || 0, liveNode.y || 0, liveNode.z || 0)
    const fromCamera = new THREE.Vector3().subVectors(camera.position, nodePos)
    if (fromCamera.lengthSq() < 1) fromCamera.set(0.12, 0.08, 1)
    fromCamera.normalize()

    // ── Safe distance: zoom tight on target so it dominates the view ──
    const isSearchMode = mode === 'search'
    const nodeRadius = Math.max(1.4, Number(liveNode.val || 2))
    const distance = 12 + nodeRadius * 1.5

    const targetCamPos = new THREE.Vector3(
      nodePos.x + fromCamera.x * distance,
      nodePos.y + fromCamera.y * distance,
      nodePos.z + fromCamera.z * distance,
    )

    // ── Sidebar-aware pan: offset camera+target so node lands in visible center ──
    const focusTarget = nodePos.clone()
    {
      const _renderer = graphRef.current?.renderer?.()
      const _dom = _renderer?.domElement
      if (_dom) {
        const fw = _dom.clientWidth, fh = _dom.clientHeight
        // Measure real visible widths from the DOM so mobile breakpoints + toggle state are honored.
        // Fall back to historical hardcoded values if refs are not yet attached.
        const _measure = (el, fallbackOpen, fallbackClosed, stillOpen) => {
          if (!el || typeof el.getBoundingClientRect !== 'function') {
            return stillOpen ? fallbackOpen : fallbackClosed
          }
          const r = el.getBoundingClientRect()
          // Off-canvas (animated out) → treat as 0. Also treat <= 32 as effectively no intrusion.
          if (!stillOpen || r.right <= 0 || r.left >= (window.innerWidth || fw) || r.width <= 32) return 0
          // Clamp intrusion to visible portion
          if (el === rightSidebarNodeRef.current) {
            return Math.max(0, (window.innerWidth || fw) - r.left)
          }
          if (el === leftSidebarNodeRef.current) {
            return Math.max(0, r.right)
          }
          // top nav: use its height
          return Math.max(0, r.bottom)
        }
        const isMobile = (window.innerWidth || fw) <= 768
        // On mobile the panels stretch full-width and eclipse the canvas; skip pan offset entirely.
        const lI = isMobile ? 0 : _measure(leftSidebarNodeRef.current, 320, 0, leftSidebarOpenRef.current)
        const rI = isMobile ? 0 : _measure(rightSidebarNodeRef.current, 384, 0, rightSidebarOpenRef.current)
        const tI = isMobile ? 0 : _measure(topNavNodeRef.current, 96, 0, topNavOpenRef.current)
        const bI = 16
        // Pixel offset from canvas center to visible area center
        const pxX = (rI - lI) / 2   // positive when right sidebar wider → shift right
        const pxY = (tI - bI) / 2   // positive when top nav present → shift up
        if (Math.abs(pxX) > 1 || Math.abs(pxY) > 1) {
          const fovRad = (camera.fov || 75) * Math.PI / 180
          const aspect = fw / fh
          const worldPerPxX = (2 * distance * Math.tan(fovRad / 2) * aspect) / fw
          const worldPerPxY = (2 * distance * Math.tan(fovRad / 2)) / fh
          const camFwd = fromCamera.clone().negate()
          const camRight = new THREE.Vector3().crossVectors(camFwd, camera.up || new THREE.Vector3(0, 1, 0)).normalize()
          const camUp = new THREE.Vector3().crossVectors(camRight, camFwd).normalize()
          const panOffset = new THREE.Vector3()
            .addScaledVector(camRight, pxX * worldPerPxX)
            .addScaledVector(camUp, pxY * worldPerPxY)
          focusTarget.add(panOffset)
          targetCamPos.add(panOffset)
        }
      }
    }

    // ── Snapshot start state ──
    const startPos = camera.position.clone()
    const controls = graphRef.current?.controls?.()
    const startLookAt = controls
      ? new THREE.Vector3().copy(controls.target)
      : new THREE.Vector3(0, 0, 0)

    // ── UI state updates ──
    applyCameraFocusFrame(true)
    setTargetLock(prev => prev.ticker === ticker && prev.phase === 'acquiring'
      ? { ...prev, phase: 'settling' }
      : prev)
    flashFocusStatus(`Settling vector: ${ticker}`, 'settle')
    if (lockSettleTimerRef.current) clearTimeout(lockSettleTimerRef.current)
    settledTargetRef.current = ''

    // ── Custom RAF flight loop ──
    const duration = isSearchMode ? 1200 : 820
    const startTime = performance.now()

    const step = (now) => {
      const elapsed = now - startTime
      const rawT = Math.min(1, elapsed / duration)
      const t = easeInOutCubic(rawT)

      // Interpolate camera position
      camera.position.lerpVectors(startPos, targetCamPos, t)

      // Look-at damping: smooth interpolation of controls target
      if (controls) {
        controls.target.lerpVectors(startLookAt, focusTarget, t)
        controls.update()
      }

      camera.updateProjectionMatrix()

      if (rawT < 1) {
        cameraFlightRef.current = { id: requestAnimationFrame(step), ticker }
      } else {
        // Flight complete — snap final position
        camera.position.copy(targetCamPos)
        if (controls) {
          controls.target.copy(focusTarget)
          controls.update()
        }
        cameraFlightRef.current = null

        // ── Settle into lock ──
        settledTargetRef.current = ticker
        setTargetLock(prev => prev.ticker === ticker
          ? { ...prev, phase: 'locked', scannerOnly: Boolean(liveNode.scanner_only) }
          : prev)
        triggerLockImpact(ticker, targetLockRef.current.source || mode || 'graph')
        flashFocusStatus(
          liveNode.scanner_only
            ? `Target settled: ${ticker} via scanner parity`
            : `Target settled: ${ticker}`,
          'lock',
        )
      }
    }

    cameraFlightRef.current = { id: requestAnimationFrame(step), ticker }
  }, [applyCameraFocusFrame, flashFocusStatus, rawNodes, triggerLockImpact])

  const getNodeThreeObject = useCallback((node) => {
    const radius = Math.max(1.4, Number(node.val || 2))
    const tint = new THREE.Color(node.color || node.baseColor || '#1e3a4a')
    const material = new THREE.MeshLambertMaterial({
      color: tint,
      emissive: tint,
      emissiveIntensity: node.emissiveInt || 0.04,
      transparent: true,
      opacity: node.hasSpark ? 0.95 : 0.75,
    })
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 14, 14), material)
    mesh.userData.nodeId = node.id
    mesh.userData.baseEmissive = node.emissiveInt || 0.04
    mesh.userData.sectorColor = node.color || node.baseColor || '#1e3a4a'
    mesh.userData.dormantColor = node.dormantColor || '#64748b'
    mesh.userData.pressureColor = node.pressureColor || node.color || node.baseColor || '#1e3a4a'
    mesh.userData.sparkColor = node.sparkTint || node.color || node.baseColor || '#1e3a4a'
    mesh.userData.hasSpark = Boolean(node.hasSpark)
    mesh.userData.nodeCore = true
    mesh.userData.shape = 'sphere'
    mesh.userData.spinRate = 0.0005
    node.__threeObj = mesh

    // Spark aura ring purged — core sphere only

    const hitTarget = new THREE.Mesh(
      new THREE.SphereGeometry(
        Math.max(radius * INTERACTION_ASSIST.hitTargetScale, INTERACTION_ASSIST.hitTargetMin),
        8,
        8,
      ),
      new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.001,
        depthWrite: false,
      }),
    )
    hitTarget.name = 'hitTarget'
    hitTarget.userData.hitTarget = true
    hitTarget.userData.nodeId = node.id
    mesh.add(hitTarget)

    return mesh
  }, [])

  const handleNodeHover = useCallback((node) => {
    setHoverData(node ? { node } : null)
    if (!node) return
    hoverMagnetRef.current = { node, ts: performance.now() }
    holdInteractionFrame(INTERACTION_ASSIST.hoverFreezeMs)
  }, [holdInteractionFrame])

  const handleNodeClick = useCallback((node) => {
    lastNodeClickAtRef.current = performance.now()
    hoverMagnetRef.current = { node, ts: lastNodeClickAtRef.current }
    holdInteractionFrame(INTERACTION_ASSIST.clickFreezeMs)
    setRightSidebarOpen(true)
    if (lockSettleTimerRef.current) clearTimeout(lockSettleTimerRef.current)
    settledTargetRef.current = ''
    setTargetLock({
      phase: 'acquiring',
      ticker: node.id,
      source: 'graph',
      rank: String(node.scanner_rank || ''),
      score: String(node.scanner_score || ''),
      form: (node.scanner_form || '').toUpperCase(),
      reason: compactReason(node.scanner_tags || node.velocityEvent?.headline || ''),
      channel: 'graph',
      scannerOnly: Boolean(node.scanner_only),
    })
    setSelectedTicker(node.id)
    setHoverData(null)
    setVisitHistory(prev => {
      const next = [node.id, ...prev.filter(t => t !== node.id)]
      return next.slice(0, 6)
    })

    // ── Pin selected node so simulation drift can't pull it away from camera focus ──
    if (pinnedNodeRef.current && pinnedNodeRef.current !== node) {
      pinnedNodeRef.current.fx = null
      pinnedNodeRef.current.fy = null
      pinnedNodeRef.current.fz = null
    }
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
      node.fx = node.x
      node.fy = node.y
      node.fz = node.z ?? 0
      pinnedNodeRef.current = node
    }

    flashFocusStatus(
      node.scanner_only ? `Acquiring target: ${node.id} via scanner parity` : `Acquiring target: ${node.id}`,
      'scan',
    )
    focusCameraToTicker(node.id, 'click')

    const scene = graphRef.current?.scene?.()

    // ── 1. Release previous orbiting peers back to their original positions ──
      orbitingPeersRef.current.forEach(peer => {
        peer.node.x = peer.origX
        peer.node.y = peer.origY
        peer.node.z = peer.origZ
        const obj = peer.node.__threeObj
        if (obj?.material) setMaterialEmissiveIntensity(obj.material, peer.node.emissiveInt || 0.04)
      })
    orbitingPeersRef.current = []

    // ── 2. Tear down previous ETF cables ─────────────────────────────────────
    if (scene) {
      etfCablesRef.current.forEach(c => { scene.remove(c); c.geometry.dispose(); c.material.dispose() })
      etfCablesRef.current = []
    }

    // Gravity rings purged — no teardown needed

    // ── 4. Tear down previous gamma wells ────────────────────────────────────
    if (scene) {
      gammaWellsRef.current.forEach(w => { scene.remove(w.mesh); w.mesh.geometry.dispose(); w.mesh.material.dispose() })
      gammaWellsRef.current = []
    }

    // ── 5. ETF Canopy Cables ──────────────────────────────────────────────────
    // Ben-David et al. (2018): mean ETF ownership 1.9% is significance floor.
    // Concave ramp separates meaningful holdings from noise.
    const etfs = node.etf_overlords || []
    if (scene && etfs.length > 0) {
      etfs.forEach((etf, i) => {
        // etf_overlords already filtered (weight >= 1.5) and pre-calc'd at ingest
        const hash  = (etf.etf || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
        const angle = (hash % 360) * (Math.PI / 180)
        const etfX  = Math.cos(angle) * (280 + (hash % 120))
        const etfZ  = Math.sin(angle) * (280 + (hash % 120))
        const etfY  = (node.y || 0) + 650 + i * 45
        const pts   = [new THREE.Vector3(node.x||0, node.y||0, node.z||0), new THREE.Vector3(etfX, etfY, etfZ)]
        const geo   = new THREE.BufferGeometry().setFromPoints(pts)
        const mat   = new THREE.LineBasicMaterial({ color: 0x4466ff, transparent: true, opacity: etf.calculatedOpacity || 0.4 })
        const cable = new THREE.Line(geo, mat)
        cable.name  = `etfCable_${etf.etf}_${i}`
        scene.add(cable)
        etfCablesRef.current.push(cable)
      })
    }

    // ── 6. Competitor Orbit — identify up to 5 peers ──────────────────────────
    const targetGravity = node.gravity || 0
    const peers = Object.values(nodeMapRef.current)
      .filter(n => n.id !== node.id && n.sector === node.sector && n.x != null)
      .sort((a, b) => Math.abs((a.gravity||0) - targetGravity) - Math.abs((b.gravity||0) - targetGravity))
      .slice(0, renderProfile.orbitPeers)

    peers.forEach((peerNode, idx) => {
      orbitingPeersRef.current.push({
        node:        peerNode,
        origX:       peerNode.x,
        origY:       peerNode.y,
        origZ:       peerNode.z || 0,
        angleOffset: (Math.PI * 2 / peers.length) * idx,
        radius:      100 + (idx % 3) * 30,
      })
    })

    // Gravity well rings purged — clean spatial field, no radar artifacts

    // ── 8. Options Gamma Well ─────────────────────────────────────────────────
    const gammaSize = node.gammaSize || 0
    if (scene && gammaSize > 0.2) {
      const wellRadius = 15 + gammaSize * 40
      const geo = new THREE.SphereGeometry(wellRadius, renderProfile.gammaSegments, renderProfile.gammaSegments)
      const mat = new THREE.MeshPhongMaterial({
        color: 0xff00ff, emissive: 0xaa00aa, emissiveIntensity: 0.8,
        transparent: true, opacity: 0.4, wireframe: true,
      })
      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.set(node.x||0, (node.y||0) - wellRadius - 20, node.z||0)
      scene.add(mesh)
      gammaWellsRef.current.push({ mesh, pullStrength: gammaSize })
    }
  }, [fgRef, flashFocusStatus, focusCameraToTicker, holdInteractionFrame, renderProfile])

  const clearTargetLock = useCallback(({ clearHash = true, restoreFilters = true } = {}) => {
    setSelectedTicker('')
    setSearchTicker('')
    setFocusStatus(null)
    setTargetLock({ ...TARGET_LOCK_IDLE })
    applyCameraFocusFrame(false)
    if (clearHash) {
      handoffConsumedRef.current = ''
      consumeHandoffHash()
    }
    if (focusRequestTimerRef.current) clearTimeout(focusRequestTimerRef.current)
    if (focusStatusTimerRef.current) clearTimeout(focusStatusTimerRef.current)
    if (lockSettleTimerRef.current) clearTimeout(lockSettleTimerRef.current)
    settledTargetRef.current = ''
    if (restoreFilters && preLockFiltersRef.current) {
      setFilters(preLockFiltersRef.current)
    }
    preLockFiltersRef.current = null

    orbitingPeersRef.current.forEach(peer => {
      peer.node.x = peer.origX
      peer.node.y = peer.origY
      peer.node.z = peer.origZ
      const obj = peer.node.__threeObj
      if (obj?.material) setMaterialEmissiveIntensity(obj.material, peer.node.emissiveInt || 0.04)
    })
    orbitingPeersRef.current = []

    // Release pinned node back to the simulation
    if (pinnedNodeRef.current) {
      pinnedNodeRef.current.fx = null
      pinnedNodeRef.current.fy = null
      pinnedNodeRef.current.fz = null
      pinnedNodeRef.current = null
    }

    const scene = graphRef.current?.scene?.()
    if (!scene) return

    etfCablesRef.current.forEach(c => { scene.remove(c); c.geometry.dispose(); c.material.dispose() })
    etfCablesRef.current = []

    gammaWellsRef.current.forEach(w => { scene.remove(w.mesh); w.mesh.geometry.dispose(); w.mesh.material.dispose() })
    gammaWellsRef.current = []

    // Dispose lock pillar
    if (lockPillarRef.current) {
      scene.remove(lockPillarRef.current)
      lockPillarRef.current.traverse?.(obj => {
        obj.geometry?.dispose?.()
        obj.material?.dispose?.()
      })
      lockPillarRef.current = null
    }

    // Cancel in-flight camera animation
    if (cameraFlightRef.current?.id) {
      cancelAnimationFrame(cameraFlightRef.current.id)
      cameraFlightRef.current = null
    }
  }, [applyCameraFocusFrame, consumeHandoffHash])

  const handleBackgroundClick = useCallback((event) => {
    const now = performance.now()
    if (now - lastNodeClickAtRef.current < INTERACTION_ASSIST.backgroundDebounceMs) return
    const magnetNode = findMagnetNodeAtPointer(event?.clientX, event?.clientY)
    if (magnetNode) {
      handleNodeClick(magnetNode)
      return
    }
    const hoverMagnet = hoverMagnetRef.current
    if (
      !selectedTickerRef.current
      && targetLockRef.current.phase === 'idle'
      && hoverMagnet?.node
      && now - Number(hoverMagnet.ts || 0) < INTERACTION_ASSIST.hoverMagnetismMs
    ) {
      handleNodeClick(hoverMagnet.node)
      return
    }
    clearTargetLock()
  }, [clearTargetLock, findMagnetNodeAtPointer, handleNodeClick])

  const requestTargetLock = useCallback(async (tickerInput, source = 'search', context = {}) => {
    const ticker = (tickerInput || '').toUpperCase().trim()
    if (!ticker) return false

    let node = rawNodes.find(n => n.id === ticker || n.ticker === ticker)

    if (!node) {
      try {
        const response = await fetch(`${API_BASE}/api/ticker/${encodeURIComponent(ticker)}`)
        if (response.ok) {
          const detail = await response.json()
          const rescuedNode = buildHudNodeFromUniverseRow({
            ticker: detail.ticker,
            name: detail.name,
            gravity: detail.gravity,
            brightness: detail.brightness,
            sector: detail.sector || detail.Sector || detail.gics_sector || detail.gics?.s || detail.industry || '',
            cap_tier: detail.cap_tier,
            etf_overlords: (detail.etf_overlords || []).filter(e => typeof e === 'object' && e.etf).map(e => ({
              ...e,
              calculatedOpacity: Math.min(0.9, 0.2 + 0.7 * Math.sqrt((e.weight || 0) / 10)),
            })),
            is_rogue: detail.is_rogue || false,
            scanner_only: detail.scanner_only,
            scanner_sources: detail.scanner_sources || [],
            scanner_rank: detail.scanner_rank,
            scanner_score: detail.scanner_score,
            scanner_form: detail.scanner_form,
            scanner_tags: detail.scanner_tags,
            scanner_link: detail.scanner_link,
            sparks: detail.sparks || null,
            velocity_event: detail.velocity_event || null,
          })
          rescuedNode.sparkHistory = []
          node = rescuedNode
          setRawNodes(prev => {
            const existingIndex = prev.findIndex(item => item.id === rescuedNode.id)
            const next = existingIndex === -1 ? [rescuedNode, ...prev] : [...prev]
            if (existingIndex !== -1) {
              next[existingIndex] = { ...prev[existingIndex], ...rescuedNode }
              nodeMapRef.current[rescuedNode.id] = next[existingIndex]
            } else {
              nodeMapRef.current[rescuedNode.id] = rescuedNode
            }
            return next
          })
        }
      } catch (error) {
        console.warn('Ticker rescue lookup failed:', error)
      }
    }

    if (!node) {
      flashFocusStatus(`No target match for ${ticker} in universe or scanner index`, 'error')
      setSearchTicker('')
      return false
    }

    setHoverData(null)
    if (lockSettleTimerRef.current) clearTimeout(lockSettleTimerRef.current)
    settledTargetRef.current = ''
    const gravityFloor = Math.max(1, Math.floor(Number(node.gravity || 0)) - 4)
    const brightnessFloor = Math.max(0, Math.floor(Number(node.brightness || 0)) - 6)
    setFilters(prev => {
      if (!preLockFiltersRef.current) preLockFiltersRef.current = prev
      return {
        ...prev,
        sector: node.sector || 'ALL',
        minGravity: Math.min(prev.minGravity, gravityFloor),
        minBrightness: Math.min(prev.minBrightness, brightnessFloor),
        sparksOnly: false,
      }
    })
    setTargetLock({
      phase: 'acquiring',
      ticker: node.id,
      source,
      rank: String(context.rank || node.scanner_rank || ''),
      score: String(context.score || node.scanner_score || ''),
      form: (context.form || node.scanner_form || '').toUpperCase(),
      reason: compactReason(context.reason || node.scanner_tags || node.velocityEvent?.headline || ''),
      channel: context.channel || '',
      scannerOnly: Boolean(node.scanner_only),
    })
    setSelectedTicker(node.id)

    // Mirror handleNodeClick behavior: push visit history so breadcrumb stays in sync.
    setVisitHistory(prev => {
      const next = [node.id, ...prev.filter(t => t !== node.id)]
      return next.slice(0, 6)
    })

    // ── Pin the node exactly like a click does ──
    // This is what makes clicking feel snappy — the d3-force simulation cannot drag
    // the node away during camera flight. Seed x/y from simulation if available,
    // otherwise pick a nearby-to-camera point so the camera has something to fly to
    // on cold-start handoff (fixes the slow scanner→cerebro perception).
    if (pinnedNodeRef.current && pinnedNodeRef.current !== node) {
      pinnedNodeRef.current.fx = null
      pinnedNodeRef.current.fy = null
      pinnedNodeRef.current.fz = null
    }
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
      node.fx = node.x
      node.fy = node.y
      node.fz = node.z ?? 0
    } else {
      // Simulation has not placed this node yet (cold handoff).
      // Seed near the current camera look-at so focus can start immediately.
      const cam = graphRef.current?.camera?.()
      const ctrl = graphRef.current?.controls?.()
      const seed = ctrl?.target
        ? { x: ctrl.target.x || 0, y: ctrl.target.y || 0, z: ctrl.target.z || 0 }
        : cam
          ? { x: (cam.position?.x || 0) * 0.2, y: (cam.position?.y || 0) * 0.2, z: 0 }
          : { x: 0, y: 0, z: 0 }
      const jitter = () => (Math.random() - 0.5) * 60
      node.x = seed.x + jitter()
      node.y = seed.y + jitter()
      node.z = seed.z + jitter() * 0.3
      node.fx = node.x
      node.fy = node.y
      node.fz = node.z
    }
    pinnedNodeRef.current = node

    holdInteractionFrame(source === 'scanner' ? INTERACTION_ASSIST.handoffFreezeMs : INTERACTION_ASSIST.clickFreezeMs)
    flashFocusStatus(
      source === 'scanner'
        ? `Scanner handoff: acquiring ${node.id}`
        : node.scanner_only
          ? `Acquiring target: ${node.id} via scanner parity`
          : `Acquiring target: ${node.id}`,
      'scan',
    )
    // Use 'click' mode so the camera flight path matches click behavior (tighter zoom, same easing).
    focusCameraToTicker(node.id, source === 'scanner' ? 'click' : 'click')
    setSearchTicker('')
    return true
  }, [flashFocusStatus, focusCameraToTicker, holdInteractionFrame, rawNodes])

  const handleSearch = useCallback(async (e) => {
    e.preventDefault()
    await requestTargetLock(searchTicker, 'search')
  }, [requestTargetLock, searchTicker])

  // ── Instant handoff feedback: fire status toast the moment the URL is parsed. ──
  // Without this, the scanner→cerebro path looks dead for 1-3 seconds while the
  // universe (10k+ nodes) loads. This gives the user an immediate "we got you" signal.
  const handoffFeedbackFiredRef = useRef(false)
  useEffect(() => {
    if (!handoffIntent?.ticker) return
    if (handoffFeedbackFiredRef.current) return
    handoffFeedbackFiredRef.current = true
    flashFocusStatus(`Scanner handoff: locking onto ${handoffIntent.ticker}…`, 'scan')
  }, [handoffIntent, flashFocusStatus])

  useEffect(() => {
    if (!handoffIntent?.ticker) return
    if (rawNodes.length === 0) return
    const handoffKey = `${handoffIntent.source}:${handoffIntent.ticker}`
    if (handoffConsumedRef.current === handoffKey) return
    handoffConsumedRef.current = handoffKey
    if ((handoffIntent.source || '').toLowerCase() === 'scanner') {
      setScannerReturnUrl(resolveScannerReturnUrl(handoffIntent))
    }
    consumeHandoffHash()
    requestTargetLock(handoffIntent.ticker, handoffIntent.source || 'scanner', handoffIntent)
      .then(locked => {
        if (!locked) {
          handoffConsumedRef.current = ''
          return
        }
      })
      .catch(error => {
        handoffConsumedRef.current = ''
        console.warn('Scanner handoff failed:', error)
      })
  }, [consumeHandoffHash, handoffIntent, rawNodes.length, requestTargetLock, resolveScannerReturnUrl, flashFocusStatus])

  const visibleVelocityEvents = useMemo(() => activeVelocityEvents(liveSparks), [liveSparks])
  const sparkRate = useMemo(() => liveEventsPerMinute(visibleVelocityEvents), [visibleVelocityEvents])
  const activeSparkCount = visibleVelocityEvents.length
  const lastEventAge = visibleVelocityEvents.length ? formatEventAge(visibleVelocityEvents[0].latest_event_ts || visibleVelocityEvents[0].ts) : '—'
  const lockPhaseStyle = TARGET_LOCK_PHASE_STYLE[targetLock.phase] || TARGET_LOCK_PHASE_STYLE.idle
  const focusToneStyle = FOCUS_STATUS_STYLE[focusStatus?.tone] || FOCUS_STATUS_STYLE.lock
  const lockStepIndex = Math.max(0, LOCK_SEQUENCE_STEPS.indexOf(targetLock.phase))
  const lockImpactVariant = lockImpact % 2 === 0 ? 'A' : 'B'
  const frameImpactAnimation = lockImpact
    ? `hudLockImpactContactFrame${lockImpactVariant} 120ms cubic-bezier(.18,.92,.28,1), hudLockImpactResonanceFrame${lockImpactVariant} 720ms cubic-bezier(.14,.84,.24,1) 88ms both`
    : 'none'
  const bloomImpactAnimation = lockImpact
    ? `hudLockImpactContactPulse${lockImpactVariant} 130ms cubic-bezier(.18,.92,.28,1), hudLockImpactResonancePulse${lockImpactVariant} 780ms cubic-bezier(.12,.84,.22,1) 74ms both`
    : 'none'
  const selectedSympathyLead = selectedTicker
    ? graphData.sympathyLeadByNode?.[selectedTicker] || null
    : null

  // Build the clickable peer list shown in NodeInspector — nodes linked by sympathy_bleed
  // edges to the selected ticker, sorted by link strength (strongest first).
  const selectedSympathyPeers = useMemo(() => {
    if (!selectedTicker) return []
    const peers = new Map()
    sympathyLinks.forEach(link => {
      const srcId = link.source?.id || link.source
      const tgtId = link.target?.id || link.target
      let peerId = null
      if (srcId === selectedTicker) peerId = tgtId
      else if (tgtId === selectedTicker) peerId = srcId
      if (!peerId || peerId === selectedTicker) return
      const strength = Number(link.sympathyStrength || 0)
      const existing = peers.get(peerId) || 0
      if (strength > existing) peers.set(peerId, strength)
    })
    return Array.from(peers.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => ({ id }))
  }, [selectedTicker, sympathyLinks])
  const activeTargetTicker = targetLock.ticker || selectedTicker || ''
  const activeTargetNode = activeTargetTicker
    ? nodeMapRef.current[activeTargetTicker] || rawNodes.find(node => node.id === activeTargetTicker) || null
    : null
  const marketPulse = useMemo(
    () => summarizeMarketPulse(visibleVelocityEvents, sympathyDensityPolicy.total),
    [sympathyDensityPolicy.total, visibleVelocityEvents],
  )

  useEffect(() => {
    marketPulseRef.current = marketPulse
  }, [marketPulse])

  useEffect(() => {
    const marker = targetMarkerRef.current
    if (!marker || !selectedNode) return
    const existing = marker.getObjectByName('metadataSprite')
    if (existing) marker.remove(existing)
    const leadLabel = selectedSympathyLead?.leader
      ? `LEAD ${selectedSympathyLead.leader}`
      : selectedNode.scanner_only
        ? 'SCANNER PARITY'
        : ''
    const sprite = makeHudBadgeSprite(
      [
        `$${selectedNode.id}`,
        `G ${Number(selectedNode.gravity || 0).toFixed(1)} · ${formatSectorLabel(selectedNode.sector)}`,
        leadLabel,
      ].filter(Boolean),
      {
        accent: selectedSympathyLead?.role === 'leader' ? '#f7c76f' : '#72e5ff',
        border: selectedSympathyLead?.leader
          ? 'rgba(247,199,111,0.28)'
          : 'rgba(114,229,255,0.28)',
        background: 'rgba(6,14,24,0.9)',
        subColor: 'rgba(214,225,238,0.8)',
        scale: 0.045,
        opacity: 0.82,
      },
    )
    if (!sprite) return
    sprite.name = 'metadataSprite'
    sprite.position.set(0, marker.userData.metadataBaseY || 18, 0)
    marker.add(sprite)
  }, [selectedNode, selectedSympathyLead])

  const sympathyLinkThreeObject = useCallback((link) => {
    if (link?.kind !== 'sympathy_bleed') return null
    const strength = Number(link?.sympathyStrength || 0)
    if (strength < FIELD_DAMPING.link.sympathyActivation) return null
    const sourceId = typeof link?.source === 'object' ? link.source?.id : link?.source
    const targetId = typeof link?.target === 'object' ? link.target?.id : link?.target
    const touchesSelection = Boolean(selectedTicker && (sourceId === selectedTicker || targetId === selectedTicker))
    const touchesHover = Boolean(hoverData?.node?.id && (sourceId === hoverData.node.id || targetId === hoverData.node.id))
    const pinnedVisible = touchesSelection || touchesHover
    if (sympathyDensityPolicy.mode === 'suppressed' && !pinnedVisible) return null
    const groupedCount = sympathyDensityPolicy.sectorSummary[link?.sympathySector || 'unknown']?.count || 1
    if (sympathyDensityPolicy.mode === 'grouped' && !pinnedVisible && !sympathyDensityPolicy.groupedKeys.has(link?.linkKey || '')) {
      return null
    }
    const positive = (link?.sympathyPolarity || 0) >= 0
    const sprite = makeHudBadgeSprite(
      [
        sympathyDensityPolicy.mode === 'grouped' && groupedCount > 1
          ? `${link?.sympathyLabel || `SYMPATHY: ${formatSectorLabel(link?.sympathySector)}`} ×${groupedCount}`
          : (link?.sympathyLabel || `SYMPATHY: ${formatSectorLabel(link?.sympathySector)}`),
      ],
      {
        accent: positive ? 'rgba(236,255,245,0.98)' : 'rgba(255,239,243,0.98)',
        border: positive ? 'rgba(95,208,170,0.36)' : 'rgba(255,122,144,0.34)',
        background: positive ? 'rgba(6,17,15,0.94)' : 'rgba(23,9,13,0.94)',
        subColor: positive ? 'rgba(207,240,222,0.86)' : 'rgba(255,206,216,0.86)',
        scale: 0.06,
        opacity: 0,
      },
    )
    if (!sprite) return null
    sprite.userData.sympathyLabel = {
      phase: Math.random(),
      lane: Number(link?.sympathyLane || 0),
      strength,
      positive,
      pinnedVisible,
    }
    return sprite
  }, [hoverData?.node?.id, selectedTicker, sympathyDensityPolicy])

  const sympathyLinkPositionUpdate = useCallback((obj, { start, end }) => {
    if (!obj || !start || !end) return
    const dx = end.x - start.x
    const dy = end.y - start.y
    const dz = (end.z || 0) - (start.z || 0)
    const planar = Math.hypot(dx, dy) || 1
    const nx = -dy / planar
    const ny = dx / planar
    const meta = obj.userData?.sympathyLabel || {}
    const lane = Number(meta.lane || 0)
    const lateral = 16 + lane * 8
    const direction = lane % 2 === 0 ? 1 : -1
    const time = performance.now() * 0.001
    const cycle = (time * 0.42 + Number(meta.phase || 0)) % 1
    const flare = cycle < 0.34 ? Math.sin((cycle / 0.34) * Math.PI) : 0
    const breathe = 0.94 + flare * 0.14
    const rise = 14 + flare * 12
    const material = obj.material
    if (material) {
      const baseOpacity = meta.pinnedVisible ? 0.18 : sympathyDensityPolicy.mode === 'suppressed' ? 0.04 : 0.08
      material.opacity = baseOpacity + flare * 0.84
    }
    const baseScale = obj.userData?.baseScale || { x: obj.scale.x, y: obj.scale.y, z: obj.scale.z || 1 }
    obj.scale.set(baseScale.x * breathe, baseScale.y * breathe, baseScale.z)
    obj.position.set(
      start.x + dx * 0.5 + nx * lateral * direction,
      start.y + dy * 0.5 + ny * lateral * direction + rise,
      (start.z || 0) + dz * 0.5,
    )
  }, [sympathyDensityPolicy.mode])

  const telemetryCards = useMemo(() => {
    const mult = macroData?.macro_pressure?.global_multiplier ?? 1.0
    const activeLock = targetLock.phase !== 'idle'
    return [
      {
        key: 'field',
        eyebrow: 'cerebro field',
        title: 'Visible Universe',
        value: `${displayedNodes.length.toLocaleString()} / ${filteredNodes.length.toLocaleString()}`,
        note: `Dense profile: ${renderProfile.name}. Rendering the highest-authority slice without choking interaction.`,
        accent: TELEMETRY_ACCENTS.cyan,
        icon: Orbit,
        span: 4,
      },
      {
        key: 'sparks',
        eyebrow: 'live tape',
        title: 'Active Sparks',
        value: `${activeSparkCount}`,
        note: `${sparkRate} events/min · last spark ${lastEventAge} · sympathy lanes ${sympathyDensityPolicy.total}`,
        accent: activeSparkCount > 0 ? TELEMETRY_ACCENTS.green : TELEMETRY_ACCENTS.gold,
        icon: Radar,
        span: 2,
      },
      {
        key: 'macro',
        eyebrow: 'macro pressure',
        title: 'Global Multiplier',
        value: `${mult.toFixed(3)}x`,
        note: `Socket ${wsStatus}. Field load ${Math.round(cognitiveLoad)}%.`,
        accent: mult >= 1.05 ? TELEMETRY_ACCENTS.green : mult <= 0.92 ? TELEMETRY_ACCENTS.rose : TELEMETRY_ACCENTS.gold,
        icon: Gauge,
        span: 2,
      },
      {
        key: 'target',
        eyebrow: activeLock ? 'active target' : 'market posture',
        title: activeLock ? `$${activeTargetTicker}` : marketPulse.bias.replace('_', ' '),
        value: activeLock ? lockPhaseStyle.label : `${Math.round(marketPulse.intensity * 100)}%`,
        note: activeLock
        ? `${activeTargetNode?.name || 'Target established on the graph'} · ${activeTargetNode?.sector || 'unknown sector'}`
          : `${marketPulse.positive} bull / ${marketPulse.negative} bear impulses. Hot ticker ${marketPulse.hottestTicker || '—'}.`,
        accent: activeLock
          ? lockPhaseStyle.tone
          : marketPulse.bias === 'bearish'
            ? TELEMETRY_ACCENTS.rose
            : marketPulse.bias === 'bullish'
              ? TELEMETRY_ACCENTS.green
              : TELEMETRY_ACCENTS.violet,
        icon: activeLock ? Target : Brain,
        span: 4,
      },
    ]
  }, [
    activeSparkCount,
    activeTargetNode?.name,
    activeTargetNode?.sector,
    activeTargetTicker,
    cognitiveLoad,
    displayedNodes.length,
    filteredNodes.length,
    lastEventAge,
    lockPhaseStyle.label,
    lockPhaseStyle.tone,
    macroData?.macro_pressure?.global_multiplier,
    marketPulse.bias,
    marketPulse.hottestTicker,
    marketPulse.intensity,
    marketPulse.negative,
    marketPulse.positive,
    renderProfile.name,
    sparkRate,
    sympathyDensityPolicy.total,
    targetLock.phase,
    wsStatus,
  ])

  const topologyStatusNote = activeTargetNode?.name
    ? `${activeTargetNode.name} · ${activeTargetNode.sector || 'unknown sector'} · ${lockPhaseStyle.modeLabel || 'target uplink'}`
    : `${marketPulse.positive} bullish impulses / ${marketPulse.negative} bearish impulses · render profile ${renderProfile.name}`

  return (
    <div className="relative w-full h-screen overflow-hidden bg-black text-white" style={{ width: '100vw', height: '100vh', background: '#000000', position: 'relative', overflow: 'hidden', isolation: 'isolate' }}>
      <style>{`
        @keyframes hudLockImpactContactFrameA {
          0% { transform: translate3d(0,0,0) scale(1); }
          35% { transform: translate3d(-3px, 1px, 0) scale(1.004); }
          70% { transform: translate3d(2px, -1px, 0) scale(1.002); }
          100% { transform: translate3d(0,0,0) scale(1); }
        }
        @keyframes hudLockImpactContactFrameB {
          0% { transform: translate3d(0,0,0) scale(1); }
          34% { transform: translate3d(3px, -1px, 0) scale(1.004); }
          72% { transform: translate3d(-2px, 1px, 0) scale(1.002); }
          100% { transform: translate3d(0,0,0) scale(1); }
        }
        @keyframes hudLockImpactResonanceFrameA {
          0% { transform: translate3d(0,0,0) scale(1); }
          24% { transform: translate3d(-1px, 0.5px, 0) scale(1.002); }
          48% { transform: translate3d(1px, -0.5px, 0) scale(1.001); }
          100% { transform: translate3d(0,0,0) scale(1); }
        }
        @keyframes hudLockImpactResonanceFrameB {
          0% { transform: translate3d(0,0,0) scale(1); }
          26% { transform: translate3d(1px, -0.5px, 0) scale(1.002); }
          50% { transform: translate3d(-1px, 0.5px, 0) scale(1.001); }
          100% { transform: translate3d(0,0,0) scale(1); }
        }
        @keyframes hudLockImpactContactPulseA {
          0% { opacity: 0; transform: scale(0.94); }
          40% { opacity: 0.62; transform: scale(1.012); }
          100% { opacity: 0; transform: scale(1.05); }
        }
        @keyframes hudLockImpactContactPulseB {
          0% { opacity: 0; transform: scale(0.95); }
          42% { opacity: 0.58; transform: scale(1.014); }
          100% { opacity: 0; transform: scale(1.048); }
        }
        @keyframes hudLockImpactResonancePulseA {
          0% { opacity: 0; transform: scale(0.98); }
          18% { opacity: 0.2; transform: scale(1.02); }
          48% { opacity: 0.16; transform: scale(1.08); }
          100% { opacity: 0; transform: scale(1.2); }
        }
        @keyframes hudLockImpactResonancePulseB {
          0% { opacity: 0; transform: scale(0.99); }
          20% { opacity: 0.18; transform: scale(1.022); }
          46% { opacity: 0.15; transform: scale(1.075); }
          100% { opacity: 0; transform: scale(1.18); }
        }
        @keyframes hudVisorSpin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes hudVisorBreath {
          0%, 100% { opacity: 0.24; transform: scale(0.985); }
          50% { opacity: 0.46; transform: scale(1.01); }
        }
        @keyframes hudHeartbeatTrace {
          0%, 100% { opacity: 0.34; transform: translateX(-12%) scaleX(0.88); }
          48% { opacity: 0.92; transform: translateX(0%) scaleX(1); }
          64% { opacity: 0.58; transform: translateX(8%) scaleX(1.04); }
        }
      `}</style>
      <div style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 380,
        opacity: 0,
        animation: bloomImpactAnimation,
        background: lockImpactMeta.source === 'scanner'
          ? 'radial-gradient(circle at center, rgba(215,180,106,0.24) 0%, rgba(114,229,255,0.16) 24%, rgba(114,229,255,0) 62%)'
          : 'radial-gradient(circle at center, rgba(95,208,170,0.22) 0%, rgba(114,229,255,0.12) 26%, rgba(114,229,255,0) 62%)',
        mixBlendMode: 'screen',
      }} />
      <div style={{ width: '100%', height: '100%' }}>
        {/* ── Top Telemetry Deck — handle fused via flex column ── */}
        <motion.div
          ref={topNavNodeRef}
          initial={false}
          animate={{ x: '-50%', y: topNavOpen ? 0 : 'calc(-100% + 24px)' }}
          transition={{ type: 'spring', bounce: 0, duration: 0.5 }}
          style={{
            position: 'fixed',
            left: '50%',
            top: 0,
            zIndex: 50,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            pointerEvents: 'none',
          }}
        >
          <div style={{ ...glassPanel(), width: '90vw', maxWidth: 1152, padding: 16, borderRadius: 24, borderTopLeftRadius: 0, borderTopRightRadius: 0, pointerEvents: 'auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 12, width: '100%' }}>
              {telemetryCards.map(card => {
                const Icon = card.icon
                return (
                  <div key={card.key} style={{
                    gridColumn: `span ${card.span}`,
                    padding: '14px 16px',
                    borderRadius: 16,
                    background: 'linear-gradient(180deg, rgba(10,18,30,0.88) 0%, rgba(7,13,22,0.72) 100%)',
                    border: `1px solid ${card.accent}33`,
                    boxShadow: `inset 0 1px 0 rgba(255,255,255,0.04), 0 0 14px ${card.accent}14`,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      {Icon && <Icon size={14} style={{ color: card.accent, opacity: 0.8 }} />}
                      <span style={{ ...monoLabel, fontSize: 8, color: card.accent }}>{card.eyebrow}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--hud-text)', marginBottom: 4 }}>{card.title}</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: card.accent, letterSpacing: '-0.02em', marginBottom: 6 }}>{card.value}</div>
                    <div style={{ fontSize: 10, color: 'var(--hud-muted)', lineHeight: 1.45 }}>{card.note}</div>
                  </div>
                )
              })}
            </div>
          </div>
          <div
            aria-label={topNavOpen ? 'Hide telemetry' : 'Show telemetry'}
            onClick={() => setTopNavOpen(v => !v)}
            style={{
              ...glassPanel('rgba(255,255,255,0.16)', 'rgba(255,255,255,0.06)'),
              width: 128,
              height: 24,
              borderRadius: '0 0 14px 14px',
              borderTop: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              pointerEvents: 'auto',
            }}
          >
            <div style={{ width: 48, height: 4, borderRadius: 999, background: 'rgba(255,255,255,0.52)' }} />
          </div>
        </motion.div>

        {/* ── Left Tactical Sidebar — handle fused ── */}
        <motion.div
          ref={leftSidebarNodeRef}
          initial={false}
          animate={{ x: leftSidebarOpen ? 0 : '-100%' }}
          transition={{ type: 'spring', bounce: 0, duration: 0.5 }}
          style={{
            position: 'fixed',
            left: 0,
            top: 96,
            bottom: 16,
            width: 320,
            zIndex: 50,
          }}
        >
          <div style={{ ...glassPanel(), width: '100%', height: '100%', padding: 16, overflowY: 'auto', borderRadius: 18, borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}>
            <ControlPanel
              embedded={true}
              filters={filters}
              setFilters={setFilters}
              sectors={sectors}
              totalNodes={filteredNodes.length}
              filteredCount={displayedNodes.length}
              sympathyDensityMode={sympathyDensityPolicy.mode}
              sympathyLabelCount={sympathyDensityPolicy.total}
              renderMode={renderProfile.name}
            />
          </div>
          <div
            aria-label={leftSidebarOpen ? 'Hide tactical controls' : 'Show tactical controls'}
            onClick={() => setLeftSidebarOpen(v => !v)}
            style={{
              position: 'absolute',
              right: -24,
              top: '50%',
              transform: 'translateY(-50%)',
              width: 24,
              height: 96,
              borderRadius: '0 12px 12px 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              ...glassPanel('rgba(255,255,255,0.16)', 'rgba(255,255,255,0.06)'),
              borderLeft: 'none',
            }}
          >
            <div style={{ width: 4, height: 32, borderRadius: 999, background: 'rgba(255,255,255,0.5)' }} />
          </div>
        </motion.div>

        {/* ── Right Command Rail — handle fused ── */}
        <motion.div
          ref={rightSidebarNodeRef}
          initial={false}
          animate={{ x: rightSidebarOpen ? 0 : '100%' }}
          transition={{ type: 'spring', bounce: 0, duration: 0.5 }}
          style={{
            position: 'fixed',
            right: 0,
            top: 96,
            bottom: 16,
            width: 384,
            zIndex: 50,
          }}
        >
          <div
            aria-label={rightSidebarOpen ? 'Hide command rail' : 'Show command rail'}
            onClick={() => setRightSidebarOpen(v => !v)}
            style={{
              position: 'absolute',
              left: -24,
              top: '50%',
              transform: 'translateY(-50%)',
              width: 24,
              height: 96,
              borderRadius: '12px 0 0 12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              ...glassPanel('rgba(255,255,255,0.16)', 'rgba(255,255,255,0.06)'),
              borderRight: 'none',
            }}
          >
            <div style={{ width: 4, height: 32, borderRadius: 999, background: 'rgba(255,255,255,0.5)' }} />
          </div>
          <div
            style={{
              ...glassPanel(),
              height: '100%',
              padding: 16,
              overflowY: 'auto',
              borderRadius: 18,
              borderTopRightRadius: 0,
              borderBottomRightRadius: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <div ref={commandCardRef} style={{
              borderRadius: 14,
              padding: '14px 16px',
              background: 'linear-gradient(180deg, rgba(10,18,30,0.88) 0%, rgba(7,13,22,0.72) 100%)',
              border: '1px solid rgba(215,180,106,0.22)',
              boxShadow: '0 14px 32px rgba(0,0,0,0.32), inset 0 1px 0 rgba(255,255,255,0.04)',
              backdropFilter: 'blur(18px)',
            }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ ...monoLabel, fontSize: 9, color: 'var(--hud-gold)' }}>Command / Search</span>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--hud-cyan)', boxShadow: '0 0 10px rgba(114,229,255,0.4)', animation: 'pulse 2s infinite' }} />
          </div>
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: 6 }}>
            <input
              type="text"
              placeholder="TICKER..."
              value={searchTicker}
              onChange={e => setSearchTicker(e.target.value)}
              style={{
                flex: 1,
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 14,
                color: 'var(--hud-text)',
                fontFamily: HUD_FONTS.mono,
                fontSize: 12,
                letterSpacing: '0.18em',
                padding: '10px 12px',
                outline: 'none',
              }}
            />
            <button type="submit" style={{
              border: '1px solid rgba(215,180,106,0.24)',
              background: 'rgba(215,180,106,0.08)',
              color: 'var(--hud-gold)', fontFamily: HUD_FONTS.mono,
              fontSize: 10, letterSpacing: '0.18em', cursor: 'pointer',
              padding: '10px 12px', borderRadius: 14, textTransform: 'uppercase',
            }}>Fly</button>
          </form>
          {(activeTargetTicker || hoverData?.node?.id) && (
            <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
              {activeTargetTicker && (
                <div ref={activeTargetCardRef} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 10,
                  padding: '9px 11px',
                  borderRadius: 14,
                  border: `1px solid ${lockPhaseStyle.border}`,
                  background: `linear-gradient(180deg, ${lockPhaseStyle.glow}, rgba(10,15,24,0.18))`,
                }}>
                  <div>
                    <div style={{ ...monoLabel, fontSize: 7, color: lockPhaseStyle.tone }}>active target</div>
                    <div style={{ marginTop: 4, color: 'var(--hud-text)', fontFamily: HUD_FONTS.display, fontSize: 15, fontWeight: 700 }}>
                      {activeTargetTicker}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-muted)' }}>
                      {targetLock.phase !== 'idle' ? lockPhaseStyle.label : 'graph focus'}
                    </div>
                    <div style={{ marginTop: 4, color: 'rgba(255,255,255,0.74)', fontSize: 10, lineHeight: 1.35, maxWidth: 148 }}>
                      {activeTargetNode?.name || 'Target acquired on the globe'}
                    </div>
                  </div>
                </div>
              )}
              {!activeTargetTicker && hoverData?.node?.id && (
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 10,
                  padding: '9px 11px',
                  borderRadius: 14,
                  border: '1px solid rgba(114,229,255,0.14)',
                  background: 'linear-gradient(180deg, rgba(114,229,255,0.06), rgba(10,15,24,0.18))',
                }}>
                  <div>
                    <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-cyan)' }}>hover track</div>
                    <div style={{ marginTop: 4, color: 'var(--hud-text)', fontFamily: HUD_FONTS.display, fontSize: 15, fontWeight: 700 }}>
                      {hoverData.node.id}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ ...monoLabel, fontSize: 7, color: 'rgba(114,229,255,0.72)' }}>click to lock</div>
                    <div style={{ marginTop: 4, color: 'rgba(255,255,255,0.7)', fontSize: 10, maxWidth: 148, lineHeight: 1.35 }}>
                      {hoverData.node.name || hoverData.node.sector || 'Target in acquisition cone'}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            {(targetLock.phase !== 'idle' || selectedNode) && (
              <button
                type="button"
                onClick={() => clearTargetLock()}
                style={{
                  flex: 1,
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: 'rgba(255,255,255,0.04)',
                  color: 'var(--hud-text)',
                  fontFamily: HUD_FONTS.mono,
                  fontSize: 10,
                  letterSpacing: '0.14em',
                  cursor: 'pointer',
                  padding: '10px 12px',
                  borderRadius: 14,
                  textTransform: 'uppercase',
                }}
              >
                Release target
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                const target = scannerReturnUrl || SCANNER_HOME_URL
                clearTargetLock()
                window.location.assign(target)
              }}
              style={{
                flex: 1,
                border: '1px solid rgba(215,180,106,0.24)',
                background: 'rgba(215,180,106,0.08)',
                color: 'var(--hud-gold)',
                fontFamily: HUD_FONTS.mono,
                fontSize: 10,
                letterSpacing: '0.14em',
                cursor: 'pointer',
                padding: '10px 12px',
                borderRadius: 14,
                textTransform: 'uppercase',
              }}
            >
              {(targetLock.source === 'scanner' || scannerReturnUrl) ? 'Back to scanner' : 'Scanner home'}
            </button>
          </div>
          {targetLock.phase !== 'idle' && (
            <div style={{
              marginTop: 10,
              padding: '12px 12px 13px',
              borderRadius: 18,
              border: `1px solid ${lockPhaseStyle.border}`,
              background: `linear-gradient(180deg, ${lockPhaseStyle.glow}, rgba(10,15,24,0.28))`,
              boxShadow: `inset 0 1px 0 rgba(255,255,255,0.03), 0 0 18px ${lockPhaseStyle.glow}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <span style={{ ...monoLabel, fontSize: 8, color: lockPhaseStyle.tone }}>
                  {targetLock.source === 'scanner' ? 'scanner handoff' : targetLock.source === 'graph' ? 'graph focus' : 'command focus'}
                </span>
                <span style={{
                  ...monoLabel,
                  fontSize: 7,
                  color: lockPhaseStyle.tone,
                  padding: '4px 8px',
                  borderRadius: 999,
                  border: `1px solid ${lockPhaseStyle.border}`,
                  background: 'rgba(255,255,255,0.02)',
                }}>
                  {lockPhaseStyle.label}
                </span>
              </div>
              <div style={{ marginTop: 10 }}>
                <div style={{
                  position: 'relative',
                  height: 6,
                  borderRadius: 999,
                  overflow: 'hidden',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.05)',
                }}>
                  <div style={{
                    width: `${lockPhaseStyle.progress * 100}%`,
                    height: '100%',
                    borderRadius: 999,
                    background: lockPhaseStyle.rail,
                    boxShadow: `0 0 16px ${lockPhaseStyle.glow}`,
                    transition: 'width 260ms ease, opacity 220ms ease',
                  }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${LOCK_SEQUENCE_STEPS.length}, minmax(0,1fr))`, gap: 8, marginTop: 8 }}>
                  {LOCK_SEQUENCE_STEPS.map((step, index) => {
                    const stepStyle = TARGET_LOCK_PHASE_STYLE[step]
                    const active = index <= lockStepIndex
                    return (
                      <div key={step} style={{
                        padding: '7px 8px',
                        borderRadius: 12,
                        border: `1px solid ${active ? stepStyle.border : 'rgba(255,255,255,0.05)'}`,
                        background: active ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.015)',
                      }}>
                        <div style={{ ...monoLabel, fontSize: 6, color: active ? stepStyle.tone : 'rgba(158,168,186,0.56)' }}>
                          {stepStyle.label}
                        </div>
                        <div style={{ marginTop: 5, color: active ? 'var(--hud-text)' : 'rgba(158,168,186,0.66)', fontSize: 10, lineHeight: 1.35 }}>
                          {stepStyle.cueLabel}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 9 }}>
                <span style={{ color: 'var(--hud-cyan)', fontWeight: 700, fontSize: 19, letterSpacing: '-0.04em', fontFamily: HUD_FONTS.display }}>
                  ${targetLock.ticker}
                </span>
                {selectedNode?.name && (
                  <span style={{ color: 'rgba(114,229,255,0.58)', fontSize: 10, textTransform: 'uppercase', fontFamily: HUD_FONTS.mono, letterSpacing: '0.14em' }}>
                    {selectedNode.name?.split(' ').slice(0, 3).join(' ')}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 8 }}>
                <div>
                  <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-muted)' }}>mechanical state</div>
                  <div style={{ marginTop: 4, color: lockPhaseStyle.tone, fontFamily: HUD_FONTS.display, fontSize: 13, fontWeight: 700 }}>
                    {lockPhaseStyle.modeLabel}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-muted)' }}>cue trigger</div>
                  <div style={{ marginTop: 4, color: 'var(--hud-text)', fontFamily: HUD_FONTS.mono, fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                    {lockPhaseStyle.cueLabel}
                  </div>
                </div>
              </div>
              {(targetLock.rank || targetLock.score || targetLock.form) && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8, marginTop: 10 }}>
                  <div style={{ padding: '8px 9px', borderRadius: 12, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-muted)' }}>handoff rank</div>
                    <div style={{ marginTop: 5, color: 'var(--hud-text)', fontFamily: HUD_FONTS.display, fontSize: 15, fontWeight: 700 }}>{targetLock.rank || '—'}</div>
                  </div>
                  <div style={{ padding: '8px 9px', borderRadius: 12, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-muted)' }}>handoff score</div>
                    <div style={{ marginTop: 5, color: 'var(--hud-gold)', fontFamily: HUD_FONTS.display, fontSize: 15, fontWeight: 700 }}>{targetLock.score || '—'}</div>
                  </div>
                  <div style={{ padding: '8px 9px', borderRadius: 12, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ ...monoLabel, fontSize: 7, color: 'var(--hud-muted)' }}>filing</div>
                    <div style={{ marginTop: 5, color: 'var(--hud-text)', fontFamily: HUD_FONTS.mono, fontSize: 13 }}>{targetLock.form || '—'}</div>
                  </div>
                </div>
              )}
              {targetLock.reason && (
                <div style={{ marginTop: 10, color: 'var(--hud-muted)', fontSize: 11, lineHeight: 1.55 }}>
                  {targetLock.reason}
                </div>
              )}
            </div>
          )}
          {focusStatus && (
            <div style={{
              marginTop: 10,
              padding: '8px 10px',
              borderRadius: 12,
              border: focusToneStyle.border,
              background: focusToneStyle.background,
              color: focusToneStyle.color,
              fontFamily: HUD_FONTS.mono,
              fontSize: 9,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}>
              {focusStatus.message}
            </div>
          )}
            </div>
          {selectedNode && (
            <Suspense fallback={<div style={{ minHeight: 320 }} />}>
              <NodeInspector
                node={selectedNode}
                sympathyLead={selectedSympathyLead}
                sympathyPeers={selectedSympathyPeers}
                visitHistory={visitHistory}
                onJumpTo={(ticker) => {
                  if (!ticker || ticker === selectedNode?.id) return
                  const target = nodeMapRef.current[ticker] || rawNodes.find(n => n.id === ticker)
                  if (!target) {
                    try { flashFocusStatus(`${ticker} not in universe`, 'error') } catch (_) {}
                    return
                  }
                  setSelectedTicker(ticker)
                  setHoverData(null)
                  setVisitHistory(prev => {
                    const next = [ticker, ...prev.filter(t => t !== ticker)]
                    return next.slice(0, 6)
                  })
                  if (pinnedNodeRef.current && pinnedNodeRef.current !== target) {
                    pinnedNodeRef.current.fx = null
                    pinnedNodeRef.current.fy = null
                    pinnedNodeRef.current.fz = null
                  }
                  if (Number.isFinite(target.x) && Number.isFinite(target.y)) {
                    target.fx = target.x
                    target.fy = target.y
                    target.fz = target.z ?? 0
                    pinnedNodeRef.current = target
                  }
                  focusCameraToTicker(ticker, 'click')
                }}
                onClose={() => clearTargetLock({ clearHash: false })}
                inline={true}
              />
            </Suspense>
          )}
          </div>
        </motion.div>
        </div>

      <div ref={graphCanvasShellRef} className="absolute inset-0 -z-20 bg-black" style={{ background: '#000000' }}>
        <CognitiveTopology
          ref={fgRef}
          graphData={graphData}
          className="absolute inset-0 h-full w-full cursor-grab"
          nodeLabel={node => `${node.id}  ${node.name}\nGravity: ${node.gravity?.toFixed(2)}  Brightness: ${node.brightness?.toFixed(2)}`}
          linkVisibility={linkVisibility}
          linkColor={neighborLinkColor}
          linkWidth={neighborLinkWidth}
          onNodeHover={handleNodeHover}
          onNodeClick={handleNodeClick}
          onNodeDrag={() => graphRef.current?.d3ReheatSimulation?.()}
          onNodeDragEnd={node => {
            node.fx = null
            node.fy = null
            node.fz = null
            graphRef.current?.d3ReheatSimulation?.()
          }}
          onBackgroundClick={handleBackgroundClick}
          backgroundColor="rgba(0,0,0,0)"
        />
      </div>
      <div
        style={{
          ...glassPanel('rgba(114, 229, 255, 0.16)', 'rgba(114, 229, 255, 0.08)'),
          position: 'fixed',
          left: '50%',
          bottom: 18,
          transform: 'translateX(-50%)',
          padding: '8px 14px',
          borderRadius: 999,
          zIndex: 52,
          pointerEvents: 'none',
        }}
      >
        <div style={{ ...monoLabel, fontSize: 8, color: 'rgba(214,225,238,0.8)' }}>
          {topologyStatusNote}
        </div>
      </div>

      {/* ── X-Ray hover overlay ── */}
      {hoverData && !selectedNode && (() => {
        const { node } = hoverData
        const { x, y } = mousePosRef.current
        const col   = node.color || '#00d4ff'
        const spark = node.sparks || {}
        const vel   = (spark.patent||0)+(spark.legal||0)+(spark.digital||0)+(spark.options||0)+(spark.weather||0)

        // Clamp so it never clips off-screen edges
        const ox = x + 18
        const oy = y - 10
        const clampX = Math.min(ox, window.innerWidth  - 220)
        const clampY = Math.min(Math.max(oy, 50), window.innerHeight - 160)

        return (
          <div style={{
            position: 'fixed',
            left: clampX, top: clampY,
            zIndex: 450,
            pointerEvents: 'none',
            width: 200,
            background: 'linear-gradient(180deg, rgba(18,20,28,0.9) 0%, rgba(10,12,18,0.82) 100%)',
            border: `1px solid ${col}44`,
            borderLeft: `2px solid ${col}`,
            borderRadius: 16,
            padding: '10px 12px',
            backdropFilter: 'blur(14px)',
            boxShadow: `0 0 20px ${col}18, 0 12px 28px rgba(0,0,0,0.42)`,
            fontFamily: HUD_FONTS.display,
            animation: 'xrayIn 0.12s ease',
          }}>
            <style>{`@keyframes xrayIn { from { opacity:0; transform:scale(0.96); } to { opacity:1; transform:scale(1); } }`}</style>

            {/* Ticker + sector */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 7, marginBottom: 7 }}>
              <span style={{ color: col, fontWeight: 700, fontSize: 16, letterSpacing: 2 }}>{node.id}</span>
              <span style={{ color: `${col}66`, fontSize: 9, textTransform: 'uppercase', letterSpacing: 1 }}>
                {node.sector || 'unknown'}
              </span>
            </div>

            {/* Bedrock row */}
            <div style={{ display: 'flex', gap: 14, borderTop: `1px solid ${col}22`, paddingTop: 6 }}>
              <div>
                <div style={{ fontSize: 8, color: '#445566', letterSpacing: 1, textTransform: 'uppercase' }}>Gravity</div>
                <div style={{ color: '#6366f1', fontWeight: 700, fontSize: 12 }}>{node.gravity?.toFixed(2)}</div>
              </div>
              <div>
                <div style={{ fontSize: 8, color: '#445566', letterSpacing: 1, textTransform: 'uppercase' }}>Brightness</div>
                <div style={{ color: '#00ffcc', fontWeight: 700, fontSize: 12 }}>{node.brightness?.toFixed(2)}</div>
              </div>
              <div>
                <div style={{ fontSize: 8, color: '#445566', letterSpacing: 1, textTransform: 'uppercase' }}>Cap</div>
                <div style={{ color: '#f59e0b', fontWeight: 700, fontSize: 12 }}>{(node.cap_tier || '—').toUpperCase()}</div>
              </div>
            </div>

            {/* Velocity if non-zero */}
            {vel !== 0 && (
              <div style={{ marginTop: 6, fontSize: 10, color: vel > 0 ? '#00ffcc' : '#ef4444', fontWeight: 700 }}>
                {vel > 0 ? '+' : ''}{vel.toFixed(1)}v TOTAL
              </div>
            )}

            {/* Tactical corner brackets */}
            <div style={{ position: 'absolute', top: -1, right: -1, width: 8, height: 8, borderTop: `1px solid ${col}`, borderRight: `1px solid ${col}` }} />
            <div style={{ position: 'absolute', bottom: -1, left: -1, width: 8, height: 8, borderBottom: `1px solid ${col}`, borderLeft: `1px solid ${col}` }} />
          </div>
        )
      })()}

      <Suspense fallback={null}>
        <VelocityDeck
          events={visibleVelocityEvents}
          onSelectTicker={(ticker) => {
            if (ticker) setSelectedTicker(ticker)
          }}
        />
      </Suspense>
    </div>
  )
}
