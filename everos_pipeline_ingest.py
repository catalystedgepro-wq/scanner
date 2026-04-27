#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from everos_memory_client import (
    EverOSRequestError,
    backend_available,
    load_config,
    render_note,
    save_messages,
)

ROOT = Path(__file__).parent


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_top_ranked(limit: int) -> list[dict[str, str]]:
    path = ROOT / "sec_catalyst_ranked.csv"
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not row:
                    continue
                rows.append(
                    {
                        "ticker": (row.get("ticker") or "").strip(),
                        "priority_score": (row.get("priority_score") or "").strip(),
                        "momentum_score": (row.get("momentum_score") or "").strip(),
                        "quality_score": (row.get("quality_score") or "").strip(),
                        "form": (row.get("form") or "").strip(),
                        "updated_utc": (row.get("updated_utc") or "").strip(),
                        "link": (row.get("link") or "").strip(),
                    }
                )
                if len(rows) >= limit:
                    break
    except Exception:
        return []
    return [row for row in rows if row.get("ticker")]


def summarize_macro() -> dict:
    layer = load_json(ROOT / "macro_layer.json")
    pressure = load_json(ROOT / "macro_pressure.json")
    pressures = pressure.get("pressures", {}) if isinstance(pressure.get("pressures"), dict) else {}

    def top_signals(reverse: bool) -> list[str]:
        ranked = sorted(
            (
                (
                    sector,
                    details.get("multiplier", 1.0),
                    details.get("signal", "neutral"),
                )
                for sector, details in pressures.items()
                if isinstance(details, dict)
            ),
            key=lambda item: item[1],
            reverse=reverse,
        )
        return [f"{sector}:{multiplier:.3f}:{signal}" for sector, multiplier, signal in ranked[:3]]

    summary = {
        "date": layer.get("date") or "",
        "environment": layer.get("environment") or "",
        "fed_funds_rate": layer.get("fed_funds_rate"),
        "treasury_10y": layer.get("treasury_10y"),
        "cpi_yoy": layer.get("cpi_yoy"),
        "m2_yoy": layer.get("m2_yoy"),
        "recession_warning": pressure.get("recession_warning"),
        "spike_alert": pressure.get("spike_alert"),
        "tailwinds": top_signals(True),
        "headwinds": top_signals(False),
    }
    return {key: value for key, value in summary.items() if value not in ("", None, [], {})}


def build_messages(mode: str, status: str, reason: str, top_limit: int) -> list[dict[str, str]]:
    scanner_status = load_json(ROOT / "scanner_artifact_status.json")
    manifest = load_json(ROOT / "pipeline_manifest.json")
    top_ranked = read_top_ranked(top_limit)
    macro = summarize_macro()

    now = datetime.now(timezone.utc).isoformat()
    counts = scanner_status.get("counts", {}) if isinstance(scanner_status.get("counts"), dict) else {}
    counts_text = ", ".join(f"{key}={value}" for key, value in counts.items()) if counts else "unavailable"
    headline = f"Cerebro scanner pipeline {status}"
    body_lines = [
        f"mode: {mode}",
        f"recorded_at: {now}",
        f"scanner_valid: {scanner_status.get('valid', False)}",
        f"display_total: {scanner_status.get('display_total', 0)}",
        f"counts: {counts_text}",
    ]
    if reason:
        body_lines.append(f"reason: {reason}")
    if scanner_status.get("reason"):
        body_lines.append(f"artifact_reason: {scanner_status.get('reason')}")
    if manifest:
        body_lines.append(f"manifest_status: {manifest.get('status', 'unknown')}")
        if manifest.get("git_short_commit"):
            body_lines.append(f"git_short_commit: {manifest.get('git_short_commit')}")
    if scanner_status.get("generated_at"):
        body_lines.append(f"scanner_generated_at: {scanner_status.get('generated_at')}")

    messages: list[dict[str, str]] = [
        {
            "role": "assistant",
            "content": render_note(
                headline,
                body="\n".join(body_lines),
                metadata={
                    "kind": "scanner_pipeline_run",
                    "mode": mode,
                    "status": status,
                },
            ),
        }
    ]

    if top_ranked:
        lines = [
            f"- {row['ticker']} {row['form']} | priority {row['priority_score']} | momentum {row['momentum_score']} | quality {row['quality_score']} | updated {row['updated_utc']}"
            for row in top_ranked
        ]
        messages.append(
            {
                "role": "assistant",
                "content": render_note(
                    "Top ranked scanner candidates",
                    body="\n".join(lines),
                    metadata={"source": "sec_catalyst_ranked.csv", "count": len(top_ranked)},
                ),
            }
        )

    if macro:
        messages.append(
            {
                "role": "assistant",
                "content": render_note(
                    "Macro layer snapshot",
                    body="Current macro context attached to this pipeline run.",
                    metadata=macro,
                ),
            }
        )

    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Scanner pipeline context into EverOS.")
    parser.add_argument("--mode", default="daily", choices=("daily", "build_only", "intraday", "ui_only", "manual"))
    parser.add_argument("--status", default="success", choices=("success", "failure"))
    parser.add_argument("--reason", default="")
    parser.add_argument("--top-limit", type=int, default=5)
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.enabled:
        print("everos_pipeline_ingest: disabled")
        return 0
    if not backend_available(cfg):
        print("everos_pipeline_ingest: backend_unavailable")
        return 0

    messages = build_messages(args.mode, args.status, args.reason.strip(), max(1, args.top_limit))
    if not messages:
        print("everos_pipeline_ingest: no_messages")
        return 0

    seed = f"pipeline:{args.status}:{args.mode}:{datetime.now(timezone.utc).date().isoformat()}"
    try:
        saved = save_messages(
            messages,
            cfg=cfg,
            flush=True,
            id_seed=seed,
            scene="cerebro_pipeline",
            raw_data_type="CerebroPipelineRun",
        )
    except EverOSRequestError as exc:
        print(f"everos_pipeline_ingest: failed ({exc})")
        return 0

    print(f"everos_pipeline_ingest: saved {saved} message(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
