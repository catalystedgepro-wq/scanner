"""api_auth.py — Lightweight API key auth for paid endpoints.

Manages API keys stored in api_keys.json.
Free tier: 10 req/hour, limited endpoints.
Paid tier: 1000 req/hour, all endpoints.

Keys are checked via X-API-Key header.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent
KEYS_FILE = ROOT / "api_keys.json"

# Endpoints that don't require auth
PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/subscribe",
    "/api/stripe-webhook",
    "/api/unlock/request",
    "/api/unlock/claim",
    "/api/unlock/verify",
    "/api/unlock/exchange",
    "/api/unlock/logout",
    "/api/admin/bootstrap",
    "/api/billing/portal",
    "/api/tier",
    "/docs",
    "/openapi.json",
    "/redoc",
})

# Endpoints available to free tier
FREE_PATHS = frozenset({
    "/api/newsletter/latest",
    "/api/newsletter/archive",
    "/api/sectors",
    "/api/macro",
})

# Rate limits
FREE_RATE = 10       # requests per hour
PAID_RATE = 1000     # requests per hour


def _load_keys() -> dict:
    if KEYS_FILE.exists():
        try:
            return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"keys": {}, "rate_log": {}}


def _save_keys(data: dict):
    KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def generate_api_key(email: str, tier: str = "free") -> str:
    """Create a new API key for a user."""
    data = _load_keys()
    raw_key = f"ce_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    data["keys"][key_hash] = {
        "email": email,
        "tier": tier,
        "created": time.time(),
        "active": True,
    }
    _save_keys(data)
    return raw_key


def validate_key(raw_key: str) -> Optional[dict]:
    """Validate an API key. Returns key info or None."""
    if not raw_key:
        return None
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    data = _load_keys()
    info = data["keys"].get(key_hash)
    if info and info.get("active", True):
        return {"hash": key_hash, **info}
    return None


def check_rate_limit(key_hash: str, tier: str) -> bool:
    """Check if key is within rate limits. Returns True if allowed."""
    data = _load_keys()
    rate_log = data.get("rate_log", {})
    now = time.time()
    hour_ago = now - 3600

    # Clean old entries
    entries = [t for t in rate_log.get(key_hash, []) if t > hour_ago]
    limit = PAID_RATE if tier == "paid" else FREE_RATE

    if len(entries) >= limit:
        return False

    entries.append(now)
    rate_log[key_hash] = entries
    data["rate_log"] = rate_log
    _save_keys(data)
    return True


def is_public_path(path: str) -> bool:
    """Check if path is public (no auth needed)."""
    return path in PUBLIC_PATHS or path.startswith("/ws/")


def is_free_path(path: str) -> bool:
    """Check if path is available to free tier."""
    return path in FREE_PATHS
