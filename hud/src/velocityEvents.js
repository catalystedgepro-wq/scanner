const SOURCE_LABELS = {
  options: "Options",
  digital: "Digital",
  patent: "Patent",
  legal: "Legal",
  weather: "Weather",
}

const LIVE_WINDOW_SECONDS = 5 * 60
const COOLING_WINDOW_SECONDS = 90 * 60
const FRESHNESS_ORDER = { live: 2, cooling: 1, stale: 0 }

const severityByMagnitude = (value) => {
  const magnitude = Math.abs(value)
  if (magnitude >= 18) return "critical"
  if (magnitude >= 10) return "high"
  if (magnitude >= 5) return "medium"
  if (magnitude > 0) return "low"
  return "dormant"
}

function freshnessFromTs(ts) {
  const age = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts || 0)))
  if (age <= LIVE_WINDOW_SECONDS) return "live"
  if (age <= COOLING_WINDOW_SECONDS) return "cooling"
  return "stale"
}

export const SEVERITY_STYLES = {
  critical: { rail: "#ff7a90", badge: "rgba(255,122,144,0.16)", text: "#ffb2bf" },
  high: { rail: "#ffbf69", badge: "rgba(255,191,105,0.16)", text: "#ffd9a3" },
  medium: { rail: "var(--hud-cyan)", badge: "rgba(114,229,255,0.14)", text: "var(--hud-cyan)" },
  low: { rail: "var(--hud-success)", badge: "rgba(70,201,118,0.14)", text: "var(--hud-success)" },
  dormant: { rail: "rgba(158,168,186,0.4)", badge: "rgba(255,255,255,0.05)", text: "var(--hud-muted)" },
}

export function velocityFreshness(event) {
  if (!event) return "stale"
  if (event.freshness) return event.freshness
  return freshnessFromTs(event.latest_event_ts || event.ts)
}

export function isVelocityEventStale(event) {
  return velocityFreshness(event) === "stale"
}

export function activeVelocityEvents(events) {
  return events.filter(event => !isVelocityEventStale(event))
}

function createFallbackEventId(ticker, spark) {
  const signature = ["patent", "legal", "digital", "options", "weather"]
    .map(key => `${key}:${Number(spark?.[key] || 0).toFixed(2)}`)
    .join("|")
  return `${ticker || "unknown"}:${signature}`
}

function normalizeLegacyComponent(key, spark) {
  const value = Number(spark?.[key] || 0)
  return {
    key,
    label: SOURCE_LABELS[key],
    short_label: SOURCE_LABELS[key],
    value,
    abs_value: Math.abs(value),
    active: Math.abs(value) > 0,
    polarity: value > 0 ? "bullish" : value < 0 ? "bearish" : "neutral",
    signal: key === "digital"
      ? (spark?.digital_signal || "")
      : key === "weather"
        ? (spark?.weather_event || "")
        : "",
  }
}

export function normalizeVelocityEvent(raw, origin = "live") {
  if (!raw) return null

  const event = raw?.velocity_event?.kind === "velocity_event" ? raw.velocity_event : raw
  const ts = Number(event?.ts || raw?.ts || Date.now() / 1000)
  const generatedAt = Number(event?.generated_at || raw?.generated_at || Date.now() / 1000)
  const latestEventTs = Number(event?.latest_event_ts || raw?.latest_event_ts || ts)
  const freshness = event?.freshness || raw?.freshness || freshnessFromTs(latestEventTs)
  const ageSeconds = Number(event?.age_seconds ?? raw?.age_seconds ?? Math.max(0, generatedAt - latestEventTs))

  if (event?.kind === "velocity_event" && event?.event_id) {
    return {
      ...event,
      ts,
      generated_at: generatedAt,
      latest_event_ts: latestEventTs,
      age_seconds: ageSeconds,
      freshness,
      is_live: freshness === "live",
      is_stale: freshness === "stale",
      origin,
      source_chips: Array.isArray(event.source_chips) ? event.source_chips : [],
      spark: event.spark || {},
      primary_driver: event.primary_driver || null,
    }
  }

  const spark = raw?.spark || raw?.sparks || {}
  const components = ["options", "digital", "patent", "legal", "weather"]
    .map(key => normalizeLegacyComponent(key, spark))
  const sourceChips = components
    .filter(component => component.active)
    .sort((left, right) => right.abs_value - left.abs_value)
  const totalVelocity = components.reduce((sum, component) => sum + component.value, 0)
  const severity = severityByMagnitude(totalVelocity)
  const primaryDriver = sourceChips[0] || null
  const polarity = totalVelocity > 0 ? "bullish" : totalVelocity < 0 ? "bearish" : "neutral"

  return {
    kind: "velocity_event",
    schema_version: "legacy-fallback",
    event_id: raw?.event_id || createFallbackEventId(raw?.ticker, spark),
    event_type: raw?.event || "velocity_event",
    wire_event: raw?.event || "velocity_event",
    ticker: raw?.ticker || "",
    name: raw?.name || "",
    ts,
    generated_at: generatedAt,
    latest_event_ts: latestEventTs,
    age_seconds: ageSeconds,
    freshness,
    is_live: freshness === "live",
    is_stale: freshness === "stale",
    origin,
    severity,
    severity_rank: { critical: 4, high: 3, medium: 2, low: 1, dormant: 0 }[severity],
    polarity,
    total_velocity: totalVelocity,
    active_sources: sourceChips.map(component => component.key),
    source_chips: sourceChips,
    primary_source: primaryDriver?.key || null,
    primary_driver: primaryDriver,
    headline: primaryDriver ? `${primaryDriver.label} driver is active` : "Velocity is dormant",
    detail: sourceChips.length > 0
      ? `Driver stack: ${sourceChips.map(component => component.short_label).join(" + ")}`
      : "No live catalyst components are active.",
    spark,
    components: Object.fromEntries(components.map(component => [component.key, component])),
  }
}

export function upsertVelocityEvent(events, nextEvent, maxItems = 8) {
  const nextFreshness = velocityFreshness(nextEvent)
  const filtered = events.filter(event => event.event_id !== nextEvent.event_id && !isVelocityEventStale(event))
  const withNext = nextFreshness === "stale" ? filtered : [nextEvent, ...filtered]
  return withNext
    .sort((left, right) => {
      const freshnessDelta = (FRESHNESS_ORDER[velocityFreshness(right)] || 0) - (FRESHNESS_ORDER[velocityFreshness(left)] || 0)
      if (freshnessDelta !== 0) return freshnessDelta
      if ((right.severity_rank || 0) !== (left.severity_rank || 0)) return (right.severity_rank || 0) - (left.severity_rank || 0)
      return Number(right.latest_event_ts || right.ts || 0) - Number(left.latest_event_ts || left.ts || 0)
    })
    .slice(0, maxItems)
}

export function liveEventsPerMinute(events) {
  const nowSeconds = Date.now() / 1000
  return events.filter(event => event.origin === "live" && nowSeconds - Number(event.latest_event_ts || event.ts || 0) <= 60).length
}

export function formatEventAge(ts) {
  if (!ts) return "—"
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts)))
  if (delta < 10) return "now"
  if (delta < 60) return `${delta}s`
  const minutes = Math.floor(delta / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h`
}
