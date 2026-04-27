#!/usr/bin/env python3
"""Per-spoke feature flag helpers.

Lets autonomous_loop.sh skip individual spokes via env vars so a single
broken spoke can't wedge the whole pipeline.

Usage:
    from ops.feature_flags import enabled, require_enabled

    if enabled("PRNEWSWIRE"):
        run_prnewswire()

    require_enabled("FEDERAL_REGISTER")  # raises if disabled
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent.parent
DEFAULTS_FILE = ROOT / "feature_flags.defaults"
LOCAL_OVERRIDE_FILE = ROOT / ".feature_flags.env"


def _load_defaults() -> dict[str, str]:
    """Read defaults from feature_flags.defaults if present.

    Format: NAME=1|0 per line, comments start with #.
    """
    out: dict[str, str] = {}
    for path in (DEFAULTS_FILE, LOCAL_OVERRIDE_FILE):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip().upper()] = v.strip()
    return out


_DEFAULTS = _load_defaults()


def enabled(name: str, default: bool = True) -> bool:
    """Return True if the spoke flag is set or default-true."""
    key = f"ENABLE_{name.upper()}"
    val = os.environ.get(key)
    if val is None:
        val = _DEFAULTS.get(key)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def require_enabled(name: str) -> None:
    """Exit cleanly if a spoke is disabled — for stand-alone scripts."""
    if not enabled(name):
        print(f"feature_flags: {name} disabled (set ENABLE_{name.upper()}=1 to run)")
        sys.exit(0)


def disabled_spokes(names: Iterable[str]) -> list[str]:
    return [n for n in names if not enabled(n)]


if __name__ == "__main__":
    # CLI: list all known flags + state.
    known = [
        "PRNEWSWIRE",
        "BUSINESSWIRE",
        "GLOBENEWSWIRE",
        "FEDERAL_REGISTER",
        "DOJ_PRESS",
        "ALPHAVANTAGE_NEWS",
        "AUTO_PROMOTE_KILL_LIST",
        "INTERACTION_SCORE",
        "LOSER_CLUSTERS",
    ]
    print(f"{'spoke':25s}  state")
    print("-" * 40)
    for n in known:
        print(f"  ENABLE_{n:18s}  {'on' if enabled(n) else 'off'}")
