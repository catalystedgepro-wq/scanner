import React, { useMemo, useState } from "react"
import { HUD_FONTS, glassPanel, monoLabel } from "./theme.js"
import { SEVERITY_STYLES, formatEventAge, velocityFreshness } from "./velocityEvents.js"

function chipStyle(chip) {
  if (chip.polarity === "bullish") {
    return {
      background: "rgba(70,201,118,0.12)",
      border: "1px solid rgba(70,201,118,0.22)",
      color: "var(--hud-success)",
    }
  }
  if (chip.polarity === "bearish") {
    return {
      background: "rgba(255,122,144,0.12)",
      border: "1px solid rgba(255,122,144,0.22)",
      color: "#ff9daf",
    }
  }
  return {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.08)",
    color: "var(--hud-muted)",
  }
}

function velocityValue(value) {
  const numeric = Number(value || 0)
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}v`
}

function compactLabel(events) {
  const highest = events[0]
  if (!highest) return "idle"
  return `${highest.ticker} ${highest.severity}`
}

function freshnessLabel(event) {
  const freshness = velocityFreshness(event)
  if (freshness === "live") return "live"
  if (freshness === "cooling") return "cooling"
  return "stale"
}

export default function VelocityDeck({ events, onSelectTicker }) {
  const [hovered, setHovered] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const handleTickerClick = (ticker) => {
    if (typeof onSelectTicker === "function" && ticker) {
      onSelectTicker(ticker)
    }
  }
  if (dismissed) {
    // Tiny restore tab so the deck never blocks the search/command UI.
    return (
      <button
        type="button"
        onClick={() => setDismissed(false)}
        title="Restore velocity deck"
        style={{
          position: "fixed",
          right: 12,
          bottom: 12,
          zIndex: 60,
          padding: "6px 10px",
          borderRadius: 999,
          background: "rgba(10,12,18,0.78)",
          border: "1px solid rgba(114,229,255,0.3)",
          color: "var(--hud-cyan)",
          fontFamily: HUD_FONTS.mono,
          fontSize: 9,
          letterSpacing: "0.08em",
          cursor: "pointer",
          opacity: 0.62,
        }}
      >
        velocity ↗
      </button>
    )
  }

  const freshestTs = useMemo(
    () => events.reduce((latest, event) => Math.max(latest, Number(event?.ts || 0)), 0),
    [events],
  )
  const freshestAge = freshestTs ? Date.now() / 1000 - freshestTs : Infinity
  const collapsed = !hovered && !pinned && freshestAge > 18
  const liveCount = events.length
  const criticalCount = events.filter(event => event.severity === "critical").length

  const shellStyle = {
    position: "fixed",
    right: 18,
    bottom: 18,
    width: collapsed ? 80 : 360,
    minHeight: collapsed ? 84 : 188,
    maxHeight: collapsed ? 110 : "42vh",
    /* Lowered from 255 → 60 so command/search overlays (z 100+) win the
     * stacking contest. Deck stays readable but never blocks UI controls. */
    zIndex: 60,
    pointerEvents: "auto",
    userSelect: "none",
    transition: "width var(--motion-medium) var(--ease-authority), opacity var(--motion-fast) var(--ease-authority), transform var(--motion-medium) var(--ease-authority), padding var(--motion-medium) var(--ease-authority)",
    opacity: collapsed ? 0.44 : 0.94,
    transform: collapsed ? "translateY(8px)" : "translateY(0)",
    overflow: "hidden",
    padding: collapsed ? "10px 10px 12px" : "14px 14px 16px",
    borderRadius: collapsed ? 26 : 28,
    background: collapsed
      ? "linear-gradient(180deg, rgba(10,12,18,0.42), rgba(10,12,18,0.24))"
      : undefined,
    ...glassPanel("rgba(114, 229, 255, 0.14)", "rgba(114, 229, 255, 0.06)"),
  }

  if (!events.length) {
    return (
      <div style={shellStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ ...monoLabel, fontSize: 9, color: "var(--hud-gold)" }}>velocity</span>
          <span style={{ fontSize: 10, color: "var(--hud-muted)" }}>Awaiting structured spark events...</span>
        </div>
      </div>
    )
  }

  if (collapsed) {
    return (
      <button
        type="button"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => setPinned(true)}
        style={{
          ...shellStyle,
          display: "grid",
          placeItems: "center",
          cursor: "pointer",
          gap: 6,
          border: "1px solid rgba(114,229,255,0.12)",
        }}
        title="Expand velocity deck"
      >
        <div style={{
          width: 26,
          height: 26,
          borderRadius: "50%",
          background: criticalCount > 0 ? "rgba(255,122,144,0.2)" : "rgba(114,229,255,0.16)",
          boxShadow: criticalCount > 0 ? "0 0 24px rgba(255,122,144,0.24)" : "0 0 24px rgba(114,229,255,0.2)",
          display: "grid",
          placeItems: "center",
          color: criticalCount > 0 ? "#ffb2bf" : "var(--hud-cyan)",
          fontFamily: HUD_FONTS.mono,
          fontSize: 10,
          letterSpacing: "0.08em",
        }}>
          {liveCount}
        </div>
        <div style={{ ...monoLabel, fontSize: 7, color: "var(--hud-muted)", textAlign: "center", lineHeight: 1.5 }}>
          {compactLabel(events)}
        </div>
      </button>
    )
  }

  return (
    <div
      style={shellStyle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ ...monoLabel, fontSize: 9, color: "var(--hud-gold)" }}>velocity deck</div>
          <div style={{ fontSize: 12, color: "var(--hud-muted)", marginTop: 4 }}>
            {velocityFreshness(events[0]) === "live"
              ? "Live authority rail. Auto-docks when the field cools so the globe stays visible."
              : "Cooling authority rail. Active pressure is fading, but the deck stays readable while the field settles."}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            onClick={() => setPinned(value => !value)}
            style={{
              border: "1px solid rgba(255,255,255,0.08)",
              background: pinned ? "rgba(215,180,106,0.12)" : "rgba(255,255,255,0.03)",
              color: pinned ? "var(--hud-gold)" : "var(--hud-muted)",
              borderRadius: 999,
              padding: "6px 10px",
              cursor: "pointer",
              ...monoLabel,
              fontSize: 7,
            }}
          >
            {pinned ? "pinned" : "auto-hide"}
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            title="Dismiss deck (small restore tab will appear)"
            style={{
              border: "1px solid rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.03)",
              color: "var(--hud-muted)",
              borderRadius: 999,
              padding: "6px 10px",
              cursor: "pointer",
              ...monoLabel,
              fontSize: 7,
            }}
          >
            ✕ hide
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <div style={{
          flex: 1,
          borderRadius: 18,
          padding: "10px 12px",
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}>
          <div style={{ ...monoLabel, fontSize: 7, color: "var(--hud-muted)" }}>live stack</div>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: HUD_FONTS.display, marginTop: 6 }}>{liveCount}</div>
        </div>
        <div style={{
          flex: 1,
          borderRadius: 18,
          padding: "10px 12px",
          background: criticalCount > 0 ? "rgba(255,122,144,0.08)" : "rgba(114,229,255,0.05)",
          border: `1px solid ${criticalCount > 0 ? "rgba(255,122,144,0.14)" : "rgba(114,229,255,0.08)"}`,
        }}>
          <div style={{ ...monoLabel, fontSize: 7, color: "var(--hud-muted)" }}>critical</div>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: HUD_FONTS.display, marginTop: 6, color: criticalCount > 0 ? "#ffb2bf" : "var(--hud-cyan)" }}>
            {criticalCount}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gap: 10, overflowY: "auto", maxHeight: "calc(42vh - 118px)", paddingRight: 4 }}>
        {events.slice(0, 6).map(event => {
          const severityStyle = SEVERITY_STYLES[event.severity] || SEVERITY_STYLES.dormant
          const primary = event.primary_driver
          const freshness = freshnessLabel(event)
          const isCooling = freshness === "cooling"
          return (
            <article
              key={event.event_id}
              role={onSelectTicker ? "button" : undefined}
              tabIndex={onSelectTicker ? 0 : undefined}
              onClick={() => handleTickerClick(event.ticker)}
              onKeyDown={(e) => {
                if (onSelectTicker && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault()
                  handleTickerClick(event.ticker)
                }
              }}
              style={{
                position: "relative",
                borderRadius: 20,
                padding: "14px 14px 12px 18px",
                background: isCooling
                  ? "linear-gradient(180deg, rgba(8,10,16,0.64), rgba(10,14,22,0.44))"
                  : "linear-gradient(180deg, rgba(8,10,16,0.78), rgba(10,14,22,0.56))",
                border: isCooling ? "1px solid rgba(255,255,255,0.04)" : "1px solid rgba(255,255,255,0.06)",
                boxShadow: isCooling ? "inset 0 1px 0 rgba(255,255,255,0.03)" : "inset 0 1px 0 rgba(255,255,255,0.04)",
                backdropFilter: isCooling ? "blur(14px)" : "blur(18px)",
                opacity: isCooling ? 0.82 : 1,
                cursor: onSelectTicker ? "pointer" : "default",
                transition: "transform 120ms ease, border-color 120ms ease",
              }}
              onMouseOver={(e) => {
                if (onSelectTicker) {
                  e.currentTarget.style.transform = "translateY(-1px)"
                  e.currentTarget.style.borderColor = "rgba(114,229,255,0.4)"
                }
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.transform = "translateY(0)"
                e.currentTarget.style.borderColor = isCooling
                  ? "rgba(255,255,255,0.04)"
                  : "rgba(255,255,255,0.06)"
              }}
            >
              <div style={{ position: "absolute", left: 0, top: 10, bottom: 10, width: 4, borderRadius: 999, background: severityStyle.rail }} />

              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: "var(--hud-text)", fontSize: 18, fontWeight: 700, fontFamily: HUD_FONTS.display, letterSpacing: "-0.03em" }}>
                      {event.ticker}
                    </span>
                    <span style={{ ...monoLabel, fontSize: 7, color: severityStyle.text, background: severityStyle.badge, border: `1px solid ${severityStyle.rail}33`, borderRadius: 999, padding: "4px 8px" }}>
                      {event.severity}
                    </span>
                    <span style={{ ...monoLabel, fontSize: 7, color: isCooling ? "rgba(202,184,149,0.82)" : "var(--hud-muted)", background: isCooling ? "rgba(202,184,149,0.08)" : "rgba(255,255,255,0.04)", border: `1px solid ${isCooling ? "rgba(202,184,149,0.16)" : "rgba(255,255,255,0.06)"}`, borderRadius: 999, padding: "4px 8px" }}>
                      {freshness}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: "var(--hud-muted)", marginTop: 5, lineHeight: 1.45 }}>
                    {event.name || "Unnamed node"}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ ...monoLabel, fontSize: 8, color: "var(--hud-muted)" }}>{formatEventAge(event.ts)}</div>
                  <div style={{ marginTop: 8, color: event.polarity === "bearish" ? "#ff9daf" : "var(--hud-cyan)", fontSize: 15, fontWeight: 700, fontFamily: HUD_FONTS.mono }}>
                    {velocityValue(event.total_velocity)}
                  </div>
                </div>
              </div>

              <div style={{ color: "var(--hud-text)", fontSize: 13, fontWeight: 700, lineHeight: 1.4, marginBottom: 8 }}>
                {event.headline}
              </div>
              <div style={{ color: "var(--hud-muted)", fontSize: 10, lineHeight: 1.6, marginBottom: 12 }}>
                {event.detail}
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
                {(event.source_chips || []).slice(0, 3).map(chip => {
                  const style = chipStyle(chip)
                  return (
                    <span
                      key={`${event.event_id}-${chip.key}`}
                      style={{
                        ...monoLabel,
                        fontSize: 7,
                        padding: "5px 8px",
                        borderRadius: 999,
                        ...style,
                      }}
                    >
                      {chip.short_label} {velocityValue(chip.value)}
                    </span>
                  )
                })}
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: "auto" }}>
                <div style={{ fontSize: 10, color: "rgba(202,184,149,0.86)", lineHeight: 1.5 }}>
                  {primary ? `${primary.label} lead` : "No active driver"}
                </div>
                <div style={{ ...monoLabel, fontSize: 8, color: "var(--hud-muted)" }}>
                  {event.event_type}
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
