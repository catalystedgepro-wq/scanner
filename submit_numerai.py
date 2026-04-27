#!/usr/bin/env python3
"""submit_numerai.py — upload weekly Numerai Signals predictions.

Uses the official `numerapi` library (handles multipart S3 upload + GraphQL
submission registration). Reads NUMERAI_PUBLIC_ID + NUMERAI_SECRET_KEY from
.sec_email_env.

Numerai Signals deadline: every Friday 14:30 UTC. Cron submits nightly so
the latest convergence-rank predictions are always staged.

Reference: https://docs.numer.ai/numerai-signals/submission-files
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
SIGNALS_CSV = ROOT / "numerai_signals.csv"
ENV_FILE = ROOT / ".sec_email_env"
LOG = ROOT / "logs/numerai_submit.log"
LOG.parent.mkdir(exist_ok=True)
STATUS = ROOT / "docs/data/numerai_submit_status.json"
STATUS.parent.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k and k not in os.environ:
            os.environ[k] = v


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def write_status(payload: dict) -> None:
    STATUS.write_text(json.dumps(payload, indent=2))


def main() -> int:
    load_env()
    public_id = os.environ.get("NUMERAI_PUBLIC_ID", "").strip()
    secret = os.environ.get("NUMERAI_SECRET_KEY", "").strip()
    model_id_override = os.environ.get("NUMERAI_MODEL_ID", "").strip() or None

    if not public_id or not secret:
        log("ABORT: NUMERAI_PUBLIC_ID or NUMERAI_SECRET_KEY missing")
        return 1
    if not SIGNALS_CSV.exists():
        log(f"ABORT: {SIGNALS_CSV.name} missing — run build_numerai_signals.py first")
        return 1

    try:
        from numerapi import SignalsAPI
    except Exception as e:
        log(f"ABORT: numerapi not installed ({e}). Run: "
            "pip3 install --user --break-system-packages numerapi")
        return 1

    api = SignalsAPI(public_id=public_id, secret_key=secret, verbosity="WARNING")

    # List models to find the Signals one
    try:
        models = api.get_models()
    except Exception as e:
        log(f"ABORT auth: {e}")
        return 1
    log(f"authed | models: {list(models.keys())}")

    if not models:
        log("ABORT: no Signals models registered. Create one at "
            "https://signals.numer.ai/account → Compute → Create model.")
        write_status({
            "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
            "ok": False, "reason": "no_signals_model",
        })
        return 1

    # Pick model
    model_name = None
    model_id = None
    if model_id_override:
        for n, mid in models.items():
            if mid == model_id_override:
                model_name, model_id = n, mid
                break
    if not model_id:
        # Pick first available
        model_name, model_id = next(iter(models.items()))
    log(f"submitting to model name={model_name} id={model_id}")

    # Upload predictions
    csv_bytes = SIGNALS_CSV.read_bytes()
    rows = csv_bytes.count(b"\n") - 1
    csv_kb = len(csv_bytes) / 1024
    log(f"uploading {csv_kb:.1f}KB / {rows} rows")

    try:
        submission_id = api.upload_predictions(
            file_path=str(SIGNALS_CSV),
            model_id=model_id,
        )
    except Exception as e:
        log(f"ABORT upload: {e}")
        write_status({
            "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
            "ok": False, "reason": str(e)[:200],
            "model_id": model_id, "model_name": model_name,
        })
        return 1

    log(f"submission_ok id={submission_id}")
    write_status({
        "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "submission_id": str(submission_id),
        "model_id": model_id,
        "model_name": model_name,
        "rows_submitted": rows,
        "csv_size_kb": round(csv_kb, 1),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
