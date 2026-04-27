# S01-D5 HUD Consumer Audit

Scope: documentation only.

This audit maps the main HUD sections and views to the backend fields and endpoints they depend on, with notes on loading, stale, and empty-state behavior. It also flags likely undocumented assumptions in the current UI contract.

## HUD Section Map

| HUD section | Backend dependency | Fields relied on | Notes |
| --- | --- | --- | --- |
| Status bar | `/api/macro` and websocket state | `macro_pressure.global_multiplier`, `macro_pressure.recession_warning`, `wsStatus`, `liveCount`, node counts | Uses defaults when macro is missing. No explicit backend health indicator is rendered. |
| Left control panel | Universe-derived local state | `sectors`, `filters`, `totalNodes`, `filteredCount`, `cognitiveLoad`, `isDeepBlue` | No direct API call. Depends on universe load succeeding first. |
| Search / command card | Universe-derived local state | `rawNodes`, `node.id`, `node.name` | Search is client-side only and assumes ticker ID equals node ID. |
| 3D graph | `/api/universe` plus `/ws/live` | `ticker`, `name`, `gravity`, `brightness`, `sector`, `cap_tier`, `etf_overlords`, `is_rogue`, live spark payload | The graph is the core consumer of the universe payload and the websocket spark stream. |
| Hover X-ray overlay | Universe-derived local state plus websocket updates | `node.id`, `node.sector`, `node.gravity`, `node.brightness`, `node.cap_tier`, `node.sparks` | Purely derived from loaded nodes and live updates. No direct fetch. |
| Weather shock overlay | `/ws/live` spark payload | `spark.weather`, `spark.weather_event`, `spark.weather_severity`, `spark.weather_state` | Only appears when the live message includes weather data. |
| Node inspector - bedrock | `/api/ticker/{symbol}` plus universe fallback | `gravity`, `brightness`, `cap_tier`, `etf_weights_sum`, `gics`, `cik` | Uses detail fetch when available, then falls back to node data. |
| Node inspector - ETF canopy | `/api/ticker/{symbol}` plus universe fallback | `etf_overlords[]`, `etf`, `weight`, `is_rogue` | Assumes ETF tether data is embedded in the ticker detail or universe record. |
| Node inspector - velocity sparks | `/api/ticker/{symbol}` plus live node state | `sparks.patent`, `sparks.legal`, `sparks.digital`, `sparks.options`, `sparks.digital_signal`, `sparks.digital_ratio`, `sparks.gamma_magnet` | Falls back to live node sparks if the detail endpoint does not have them. |
| Node inspector - AI module | `/api/ai-summary/{ticker}` | `summary`, `confidence`, `catalyst_type`, `filing_type`, `filing_date`, `source` | Shows a pending state when the endpoint is offline or non-200. |
| Live feed ticker | `/ws/live` | `event`, `ticker`, `ts`, `spark`, spark velocity components | Ignores heartbeat messages and only renders entries with `ticker`. |

## Endpoint Contract Notes

### `GET /api/universe`

Expected shape:

```json
{
  "total": 123,
  "page": 1,
  "per_page": 500,
  "pages": 1,
  "tickers": [
    {
      "ticker": "ABC",
      "name": "Example Co",
      "gravity": 4.2,
      "brightness": 7.8,
      "sector": "Technology",
      "cap_tier": "mega",
      "etf_overlords": [],
      "is_rogue": false
    }
  ]
}
```

The HUD loader also tolerates a raw array, but the intended contract is paginated JSON. The current implementation assumes the field names above when building the graph.

### `GET /api/ticker/{symbol}`

Expected shape:

```json
{
  "ticker": "ABC",
  "name": "Example Co",
  "gravity": 4.2,
  "brightness": 7.8,
  "mkt_cap_usd": 0,
  "cap_tier": "mega",
  "gics": { "s": "Technology", "i": "Software", "si": "Application Software" },
  "etf_weights_sum": 0.0,
  "sparks": {
    "patent": 0,
    "legal": 0,
    "digital": 0,
    "digital_signal": "",
    "digital_ratio": 1.0,
    "options_vel": 0
  },
  "geospatial_nodes": [],
  "cik": ""
}
```

The inspector expects `gics` to be an object and not a string. It also expects `sparks` to be nested under `sparks`, not flattened.

### `GET /api/macro`

Expected shape:

```json
{
  "macro_layer": {},
  "macro_pressure": {
    "global_multiplier": 1.0,
    "recession_warning": false
  }
}
```

The status bar only reads `macro_pressure.global_multiplier` and `macro_pressure.recession_warning`. Missing keys default safely in the UI.

### `GET /api/ai-summary/{ticker}`

Expected shape:

```json
{
  "summary": "two sentence catalyst summary",
  "confidence": 0.91,
  "catalyst_type": "REVENUE_BEAT",
  "filing_type": "8-K",
  "filing_date": "2026-04-07",
  "source": "haiku"
}
```

The HUD also treats any non-200 response as a graceful pending state.

### `GET /api/briefing`

Not currently rendered in the HUD, but relevant to future operator audio workflows.

### `WS /ws/live`

The HUD currently assumes live websocket messages look like:

```json
{
  "event": "spark",
  "ticker": "ABC",
  "ts": 1712520000,
  "spark": {
    "patent": 0,
    "legal": 0,
    "digital": 0,
    "options": 0,
    "weather": 0
  }
}
```

Heartbeat messages are ignored when `event === "heartbeat"`.

## Loading, Empty, and Stale-State Expectations

- Universe loading has no dedicated spinner. The graph starts empty and fills once `/api/universe` returns.
- Macro loading is silent. The status bar falls back to `1.0x` and no recession warning if macro data is missing.
- Websocket reconnects are visible through the status indicator. A disconnected socket should show a reconnecting state.
- Live feed empty state is explicit: it shows "awaiting velocity events..." when no sparks have arrived.
- Node inspector loading is explicit: it shows "Loading intelligence..." while the detail fetch is in flight.
- AI summary missing or offline state is explicit: it shows "Analysis pending - endpoint offline."
- Stale universe or stale websocket data is not visibly timestamped in the HUD today. Freshness is implied, not surfaced.

## Likely Undocumented Assumptions

1. `node.id` and ticker symbol are treated as the same value everywhere.
2. `node.sector` from `/api/universe` is assumed to be a usable display value, not just an internal code.
3. `etf_overlords` is assumed to be an array of objects with `etf` and `weight`.
4. `gics` is assumed to be an object with at least `s`, and often `i` and `si`.
5. The websocket payload is assumed to use `spark` as the nested field name.
6. The websocket payload is assumed to provide `ts` in Unix seconds.
7. Live spark records are assumed to expose `patent`, `legal`, `digital`, `options`, and optional `weather`.
8. The node detail endpoint is assumed to provide `cik` for the EDGAR link.
9. `gammaSize` is used in the 3D selection physics, but it is not clearly documented in the backend contract.
10. `cap_tier` is used for display even though the backend also permits `mkt_cap_tier`, creating a naming fallback that should be documented.

## Most Important UI Contract Risks

- Websocket shape mismatch risk: the API docstring describes `{event, ticker, data, ts}`, while the HUD expects `{event, ticker, spark, ts}`. If production publishes `data` instead of `spark`, the live feed and weather overlay will silently fail.
- Freshness visibility risk: the HUD has no visible timestamp or data-age marker for universe or macro state, so stale backend data can look current.
- Field alias risk: `cap_tier` versus `mkt_cap_tier` is handled by fallback, but the preferred canonical field is not documented in the UI contract.
- Detail/schema risk: the inspector expects `gics` to be a structured object and `sparks` to be nested, so a flattened or renamed backend payload would break the view.
- AI endpoint risk: the inspector degrades gracefully on non-200, but it assumes the response schema will remain stable when the endpoint is live.
- Selection-physics risk: `gammaSize` drives selection effects in the HUD, but the backend contract does not clearly define where that value comes from.

## Recommendation

Document the websocket payload as the highest-priority contract item before expanding HUD features. After that, add explicit freshness indicators for universe and macro data so stale backend state cannot masquerade as live truth.
