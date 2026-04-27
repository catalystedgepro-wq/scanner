#!/usr/bin/env python3
"""Write Cerebro's provider contract into OpenBB user_settings.json."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data_contract import build_openbb_user_settings, openbb_pilot_settings


def main() -> int:
    settings = openbb_pilot_settings()
    target_dir = Path(settings["settings_dir"]).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "user_settings.json"

    payload = build_openbb_user_settings()
    target_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "settings_path": str(target_path),
                "openbb_enabled": settings["enabled"],
                "macro_provider_priority": settings["macro_provider_priority"],
                "crypto_provider_priority": settings["crypto_provider_priority"],
                "credential_keys": sorted(payload.get("credentials", {}).keys()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
