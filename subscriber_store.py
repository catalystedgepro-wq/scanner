"""subscriber_store.py — Single source of truth for paid subscribers.

Cookie = identity (signed email).
subscribers.json = license (status + period end + tier).
/api/tier checks THIS file on every request — that's how we lock people
after a month when their payment fails or they cancel.

In-memory cache with 60s TTL + mtime check keeps `/api/tier` cheap at scale.
Swap the JSON read for SQLite/Postgres later — function signatures stay.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
STORE_FILE = ROOT / "subscribers.json"

_CACHE_TTL_SECONDS = 60
_lock = threading.Lock()
_cache: dict = {"loaded_at": 0.0, "mtime": 0.0, "by_email": {}}


def _load_from_disk() -> dict[str, dict]:
    if not STORE_FILE.exists():
        return {}
    try:
        raw = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict] = {}
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        email = (rec.get("email") or "").strip().lower()
        if not email:
            continue
        out[email] = rec
    return out


def _get_all() -> dict[str, dict]:
    now = time.time()
    with _lock:
        mtime = STORE_FILE.stat().st_mtime if STORE_FILE.exists() else 0.0
        fresh = (now - _cache["loaded_at"]) < _CACHE_TTL_SECONDS
        unchanged = mtime == _cache["mtime"]
        if fresh and unchanged and _cache["by_email"]:
            return _cache["by_email"]
        _cache["by_email"] = _load_from_disk()
        _cache["loaded_at"] = now
        _cache["mtime"] = mtime
        return _cache["by_email"]


def _invalidate() -> None:
    with _lock:
        _cache["loaded_at"] = 0.0
        _cache["mtime"] = 0.0
        _cache["by_email"] = {}


def get_subscriber(email: str) -> Optional[dict]:
    if not email:
        return None
    return _get_all().get(email.strip().lower())


def subscription_status(email: str) -> dict:
    """Return {tier, status, active, period_end}. `active` is the gate."""
    rec = get_subscriber(email)
    if not rec:
        return {"tier": "free", "status": "none", "active": False, "period_end": None}
    status = (rec.get("status") or ("active" if rec.get("active") else "canceled")).lower()
    period_end = rec.get("current_period_end")
    tier = (rec.get("tier") or "pro").lower()
    now = int(time.time())
    if period_end is not None:
        try:
            period_end = int(period_end)
        except (TypeError, ValueError):
            period_end = None
    within_period = period_end is None or period_end > now
    active = status == "active" and within_period
    return {"tier": tier, "status": status, "active": active, "period_end": period_end}


def is_active_subscriber(email: str) -> bool:
    return subscription_status(email).get("active", False)


def upsert_subscriber(email: str, **fields) -> dict:
    """Atomic upsert. Returns the stored record."""
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email required")
    with _lock:
        records: list[dict] = []
        if STORE_FILE.exists():
            try:
                loaded = json.loads(STORE_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    records = loaded
            except (json.JSONDecodeError, ValueError):
                records = []
        found_idx = -1
        for i, rec in enumerate(records):
            if (rec.get("email") or "").strip().lower() == email:
                found_idx = i
                break
        if found_idx < 0:
            record = {
                "email": email,
                "joined": time.strftime("%Y-%m-%d"),
                "source": fields.get("source", "stripe"),
            }
            records.append(record)
            found_idx = len(records) - 1
        record = records[found_idx]
        for k, v in fields.items():
            record[k] = v
        record["updated_at"] = int(time.time())
        if "active" not in record and "status" in record:
            record["active"] = record["status"] == "active"
        STORE_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")
        _cache["loaded_at"] = 0.0
    return record


def mark_status(email: str, status: str, period_end: Optional[int] = None) -> dict:
    fields = {"status": status, "active": status == "active"}
    if period_end is not None:
        fields["current_period_end"] = int(period_end)
    return upsert_subscriber(email, **fields)
