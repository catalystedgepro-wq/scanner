from __future__ import annotations

import time
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

VELOCITY_DECK_SCHEMA_VERSION = "2026-04-07-vdeck-01"
VELOCITY_EVENT_LIVE_WINDOW_SECONDS = 5 * 60
VELOCITY_EVENT_COOLING_WINDOW_SECONDS = 90 * 60

_SOURCE_META: dict[str, dict[str, str]] = {
    "options": {
        "label": "Options",
        "short_label": "Options",
        "headline_bullish": "Options flow is pulling attention higher",
        "headline_bearish": "Options flow is leaning against the node",
        "headline_neutral": "Options flow is active around the node",
    },
    "digital": {
        "label": "Digital",
        "short_label": "Digital",
        "headline_bullish": "Digital attention is accelerating",
        "headline_bearish": "Digital attention is fading",
        "headline_neutral": "Digital attention is active",
    },
    "patent": {
        "label": "Patent",
        "short_label": "Patent",
        "headline_bullish": "Innovation flow is brightening the node",
        "headline_bearish": "Patent activity is mixed",
        "headline_neutral": "Patent activity is active",
    },
    "legal": {
        "label": "Legal",
        "short_label": "Legal",
        "headline_bullish": "Legal pressure is easing",
        "headline_bearish": "Legal pressure is dragging on the node",
        "headline_neutral": "Legal pressure is active",
    },
    "weather": {
        "label": "Weather",
        "short_label": "Weather",
        "headline_bullish": "Weather recovery demand is building",
        "headline_bearish": "Weather disruption is hitting the node",
        "headline_neutral": "Weather exposure is active",
    },
}

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "dormant": 0}
_SPARK_KEYS = ("patent", "legal", "digital", "options", "weather")
_SPARK_TS_KEYS = tuple(f"{key}_ts" for key in _SPARK_KEYS)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_epoch(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        epoch = float(value)
        return epoch if epoch > 0 else None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def _freshness_band(age_seconds: float) -> str:
    if age_seconds <= VELOCITY_EVENT_LIVE_WINDOW_SECONDS:
        return "live"
    if age_seconds <= VELOCITY_EVENT_COOLING_WINDOW_SECONDS:
        return "cooling"
    return "stale"


def canonical_spark_snapshot(entry: dict | None) -> dict:
    entry = entry or {}
    options_signals = entry.get("options_signals") or []
    if not isinstance(options_signals, list):
        options_signals = [str(options_signals)]
    snapshot = {
        "patent": round(_to_float(entry.get("patent")), 4),
        "legal": round(_to_float(entry.get("legal")), 4),
        "digital": round(_to_float(entry.get("digital")), 4),
        "options": round(_to_float(entry.get("options")), 4),
        "weather": round(_to_float(entry.get("weather")), 4),
        "digital_signal": str(entry.get("digital_signal") or ""),
        "digital_ratio": round(_to_float(entry.get("digital_ratio") or 1.0), 4),
        "options_signals": [str(v) for v in options_signals if str(v).strip()][:3],
        "gamma_magnet": entry.get("gamma_magnet"),
        "patent_count": entry.get("patent_count"),
        "latest_patent": str(entry.get("latest_patent") or ""),
        "weather_event": str(entry.get("weather_event") or ""),
        "weather_severity": str(entry.get("weather_severity") or ""),
        "weather_state": str(entry.get("weather_state") or ""),
    }
    for key in _SPARK_TS_KEYS:
        snapshot[key] = str(entry.get(key) or "")
    return snapshot


def spark_total(snapshot: dict | None) -> float:
    snap = canonical_spark_snapshot(snapshot)
    return round(sum(_to_float(snap.get(key)) for key in _SPARK_KEYS), 4)


def _component_signal(key: str, snapshot: dict) -> str:
    if key == "digital":
        return snapshot.get("digital_signal", "")
    if key == "options":
        return ", ".join(snapshot.get("options_signals") or [])
    if key == "weather":
        parts = [snapshot.get("weather_event", ""), snapshot.get("weather_severity", "")]
        return " ".join(part for part in parts if part).strip()
    if key == "patent":
        return snapshot.get("latest_patent", "")
    return ""


def _component_ts(key: str, snapshot: dict) -> float | None:
    return _to_epoch(snapshot.get(f"{key}_ts"))


def _event_ts(snapshot: dict, active: list[dict], fallback_ts: float | None) -> tuple[float, bool]:
    source_ts = [
        component_ts
        for component in active
        for component_ts in [_component_ts(component["key"], snapshot)]
        if component_ts is not None
    ]
    if source_ts:
        return max(source_ts), True
    fallback = float(fallback_ts) if fallback_ts is not None else time.time()
    return fallback, False


def _component_polarity(value: float) -> str:
    if value > 0:
        return "bullish"
    if value < 0:
        return "bearish"
    return "neutral"


def _severity(total_velocity: float) -> str:
    magnitude = abs(total_velocity)
    if magnitude >= 18:
        return "critical"
    if magnitude >= 10:
        return "high"
    if magnitude >= 5:
        return "medium"
    if magnitude > 0:
        return "low"
    return "dormant"


def _event_type(primary_source: str | None, active_count: int) -> str:
    if active_count > 1:
        return "velocity_stack"
    return {
        "options": "options_flow",
        "digital": "digital_buzz",
        "patent": "innovation_signal",
        "legal": "legal_risk",
        "weather": "weather_shock",
    }.get(primary_source or "", "velocity_event")


def _headline(primary_source: str | None, polarity: str, active_count: int) -> str:
    if not primary_source:
        return "Velocity is dormant"
    if active_count > 1:
        if polarity == "bullish":
            return "Multiple catalysts are stacking bullish pressure"
        if polarity == "bearish":
            return "Multiple catalysts are stacking bearish pressure"
        return "Multiple catalysts are stacking on the node"
    meta = _SOURCE_META[primary_source]
    if polarity == "bullish":
        return meta["headline_bullish"]
    if polarity == "bearish":
        return meta["headline_bearish"]
    return meta["headline_neutral"]


def _detail(primary: dict | None, active: list[dict]) -> str:
    if not active:
        return "No live catalyst components are active."
    labels = " + ".join(component["short_label"] for component in active[:3])
    if primary and primary.get("signal"):
        return f"Driver stack: {labels} | {primary['signal']}"
    return f"Driver stack: {labels}"


def _signature(ticker: str, snapshot: dict) -> str:
    parts = [ticker.upper()]
    for key in _SPARK_KEYS:
        parts.append(f"{key}:{_to_float(snapshot.get(key)):.2f}")
    parts.extend([
        snapshot.get("digital_signal", ""),
        ",".join(snapshot.get("options_signals") or []),
        snapshot.get("weather_event", ""),
        snapshot.get("weather_severity", ""),
        snapshot.get("weather_state", ""),
    ])
    raw = "|".join(parts)
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_velocity_event(
    ticker: str,
    snapshot: dict | None,
    *,
    name: str = "",
    wire_event: str = "spark_update",
    ts: float | None = None,
) -> dict:
    snap = canonical_spark_snapshot(snapshot)
    total = spark_total(snap)
    polarity = _component_polarity(total)
    components = []
    for key in _SPARK_KEYS:
        value = _to_float(snap.get(key))
        meta = _SOURCE_META[key]
        component = {
            "key": key,
            "label": meta["label"],
            "short_label": meta["short_label"],
            "value": round(value, 4),
            "abs_value": round(abs(value), 4),
            "active": abs(value) > 0,
            "polarity": _component_polarity(value),
            "signal": _component_signal(key, snap),
        }
        if key == "digital":
            component["ratio"] = snap.get("digital_ratio", 1.0)
        if key == "options" and snap.get("gamma_magnet") is not None:
            component["gamma_magnet"] = snap.get("gamma_magnet")
        if key == "patent" and snap.get("patent_count") is not None:
            component["count"] = snap.get("patent_count")
        if key == "weather":
            component["state"] = snap.get("weather_state", "")
            component["severity"] = snap.get("weather_severity", "")
        components.append(component)

    active = sorted(
        [component for component in components if component["active"]],
        key=lambda component: (-component["abs_value"], component["key"]),
    )
    primary = active[0] if active else None
    severity = _severity(total)
    generated_at = time.time()
    event_ts, has_source_timestamp = _event_ts(snap, active, ts)
    age_seconds = max(0.0, generated_at - event_ts)
    freshness = _freshness_band(age_seconds)
    return {
        "schema_version": VELOCITY_DECK_SCHEMA_VERSION,
        "kind": "velocity_event",
        "event_id": _signature(ticker, snap),
        "wire_event": wire_event,
        "event_type": _event_type(primary["key"] if primary else None, len(active)),
        "ticker": ticker.upper(),
        "name": name,
        "ts": event_ts,
        "generated_at": generated_at,
        "latest_event_ts": event_ts,
        "age_seconds": round(age_seconds, 2),
        "freshness": freshness,
        "is_live": freshness == "live",
        "is_stale": freshness == "stale",
        "has_source_timestamp": has_source_timestamp,
        "severity": severity,
        "severity_rank": _SEVERITY_ORDER[severity],
        "polarity": polarity,
        "total_velocity": total,
        "active_sources": [component["key"] for component in active],
        "source_chips": active,
        "primary_source": primary["key"] if primary else None,
        "primary_driver": primary,
        "headline": _headline(primary["key"] if primary else None, polarity, len(active)),
        "detail": _detail(primary, active),
        "spark": snap,
        "components": {component["key"]: component for component in components},
    }
