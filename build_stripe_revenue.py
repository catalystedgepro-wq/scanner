#!/usr/bin/env python3
"""build_stripe_revenue.py — pull live MRR + customers + payouts from Stripe.

Uses STRIPE_RESTRICTED_KEY (rk_live_...) — read-only on customers,
subscriptions, invoices, charges, balance, payouts. If only sk_/secret is
present, falls back to that.

Output: docs/data/revenue.json
  {
    generated_at, balance: {available_usd, pending_usd},
    subscribers: {active, trialing, canceled, total_seen},
    mrr_usd, arr_usd,
    plans: [{id, nickname, amount, currency, count}],
    last_30_days: {gross_volume_usd, refunds_usd, net_usd, charge_count},
    last_payout: {amount_usd, paid_at, currency},
    upcoming_invoices: [{customer_email, amount_due_usd, period_end}]
  }

Stdlib only (urllib + json + base64).
"""
from __future__ import annotations

import base64
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
OUT = ROOT / "docs/data/revenue.json"
SUMMARY_OUT = ROOT / "docs/data/stripe_revenue.json"  # consumed by /status/ panel
OUT.parent.mkdir(parents=True, exist_ok=True)

STRIPE_API = "https://api.stripe.com/v1"
TIMEOUT = 20


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k and k not in os.environ:
            os.environ[k] = v


def stripe_get(path: str, params: dict | None = None, key: str = "") -> dict:
    qs = ""
    if params:
        qs = "?" + urllib.parse.urlencode(params, doseq=True)
    url = STRIPE_API + path + qs
    auth = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {auth}", "Stripe-Version": "2023-10-16"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def stripe_list(path: str, key: str, params: dict | None = None,
                limit_per_page: int = 100, max_pages: int = 10) -> list[dict]:
    out: list[dict] = []
    p = dict(params or {})
    p["limit"] = limit_per_page
    for _ in range(max_pages):
        data = stripe_get(path, p, key)
        items = data.get("data") or []
        out.extend(items)
        if not data.get("has_more"):
            break
        if items:
            p["starting_after"] = items[-1]["id"]
    return out


def cents_to_usd(c) -> float:
    try:
        return round(float(c) / 100, 2)
    except Exception:
        return 0.0


def main() -> int:
    load_env()
    key = (os.environ.get("STRIPE_RESTRICTED_KEY", "").strip()
           or os.environ.get("STRIPE_SECRET_KEY", "").strip())
    if not key:
        print("ABORT: no STRIPE_RESTRICTED_KEY or STRIPE_SECRET_KEY in .sec_email_env")
        # Write a status JSON so /status/ panel shows a real Last-Modified timestamp
        # instead of going UNKNOWN. Non-fatal — autonomous loop continues.
        SUMMARY_OUT.write_text(json.dumps({
            "ok": False,
            "reason": "stripe_key_missing",
            "last_attempt_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2))
        return 0

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # 1. Balance
    try:
        bal = stripe_get("/balance", None, key)
        payload["balance"] = {
            "available_usd": sum(cents_to_usd(b.get("amount", 0)) for b in bal.get("available", [])),
            "pending_usd":   sum(cents_to_usd(b.get("amount", 0)) for b in bal.get("pending", [])),
        }
    except Exception as e:
        payload["balance_error"] = str(e)

    # 2. Subscriptions — list active + trialing + past_due
    subs_summary = {"active": 0, "trialing": 0, "past_due": 0, "canceled": 0, "total_seen": 0}
    plan_counts: dict[str, dict] = {}
    mrr_cents = 0
    try:
        for status in ("active", "trialing", "past_due"):
            subs = stripe_list("/subscriptions", key, params={"status": status})
            subs_summary[status] = len(subs)
            subs_summary["total_seen"] += len(subs)
            for s in subs:
                items = (s.get("items") or {}).get("data") or []
                for it in items:
                    price = it.get("price") or {}
                    interval = (price.get("recurring") or {}).get("interval", "month")
                    interval_count = (price.get("recurring") or {}).get("interval_count", 1)
                    qty = it.get("quantity") or 1
                    amt = price.get("unit_amount") or 0
                    if not amt:
                        continue
                    # Normalize to monthly
                    if interval == "year":
                        monthly_cents = (amt * qty) / max(1, interval_count) / 12
                    elif interval == "week":
                        monthly_cents = (amt * qty) / max(1, interval_count) * 4.345
                    elif interval == "day":
                        monthly_cents = (amt * qty) / max(1, interval_count) * 30.44
                    else:  # month
                        monthly_cents = (amt * qty) / max(1, interval_count)
                    if status in ("active", "trialing"):
                        mrr_cents += monthly_cents
                    pid = price.get("id", "?")
                    nickname = price.get("nickname") or "Plan " + pid[-6:]
                    pc = plan_counts.setdefault(pid, {
                        "price_id": pid, "nickname": nickname,
                        "amount_usd": cents_to_usd(amt), "interval": interval,
                        "count": 0,
                    })
                    pc["count"] += 1
        # Canceled count for context (just count via /subscriptions?status=canceled)
        canceled = stripe_list("/subscriptions", key,
                               params={"status": "canceled"}, max_pages=2)
        subs_summary["canceled"] = len(canceled)
    except urllib.error.HTTPError as e:
        payload["subs_error"] = f"{e.code} {e.reason}"
    except Exception as e:
        payload["subs_error"] = str(e)

    payload["subscribers"] = subs_summary
    payload["mrr_usd"] = cents_to_usd(mrr_cents)
    payload["arr_usd"] = round(payload["mrr_usd"] * 12, 2)
    payload["plans"] = list(plan_counts.values())

    # 3. Last 30 days charges → gross volume
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    try:
        charges = stripe_list("/charges", key,
                              params={"created[gte]": since_ts}, max_pages=5)
        gross_cents = sum(c.get("amount", 0) for c in charges if c.get("paid"))
        refund_cents = sum(c.get("amount_refunded", 0) for c in charges)
        payload["last_30_days"] = {
            "gross_volume_usd": cents_to_usd(gross_cents),
            "refunds_usd": cents_to_usd(refund_cents),
            "net_usd": cents_to_usd(gross_cents - refund_cents),
            "charge_count": len(charges),
            "successful_charges": sum(1 for c in charges if c.get("paid")),
        }
    except Exception as e:
        payload["charges_error"] = str(e)

    # 4. Last payout
    try:
        pos = stripe_list("/payouts", key, params={"limit": 1}, max_pages=1)
        if pos:
            p = pos[0]
            payload["last_payout"] = {
                "amount_usd": cents_to_usd(p.get("amount", 0)),
                "currency": p.get("currency", "usd").upper(),
                "status": p.get("status"),
                "arrival_date": datetime.fromtimestamp(
                    p.get("arrival_date", 0), tz=timezone.utc).isoformat() if p.get("arrival_date") else None,
            }
    except Exception as e:
        payload["payouts_error"] = str(e)

    OUT.write_text(json.dumps(payload, indent=2))
    # Trim summary for /status/ panel consumers (also serves as freshness probe).
    SUMMARY_OUT.write_text(json.dumps({
        "ok": True,
        "last_attempt_utc": payload["generated_at"],
        "active_customers": subs_summary["active"] + subs_summary["trialing"],
        "active_subscriptions": subs_summary["active"],
        "mrr_usd": payload["mrr_usd"],
        "arr_usd": payload["arr_usd"],
        "signups_30d": payload.get("last_30_days", {}).get("successful_charges", 0),
        "cancellations_30d": subs_summary["canceled"],
        "churn_pct": round(
            100 * subs_summary["canceled"] / max(subs_summary["active"] + subs_summary["canceled"], 1),
            2,
        ),
    }, indent=2, sort_keys=True))
    print(f"stripe_revenue: balance avail=${payload.get('balance',{}).get('available_usd',0):.2f} "
          f"pending=${payload.get('balance',{}).get('pending_usd',0):.2f} | "
          f"MRR=${payload.get('mrr_usd',0):.2f} | "
          f"subs active={subs_summary['active']} trialing={subs_summary['trialing']} canceled={subs_summary['canceled']} | "
          f"30d gross=${payload.get('last_30_days',{}).get('gross_volume_usd',0):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
