#!/usr/bin/env python3
"""build_clinicaltrials.py — ClinicalTrials.gov industry Phase 2/3 tape.

Recently updated Phase 2/3 industry-sponsored trials. Signal: trial
status transitions (RECRUITING -> ACTIVE_NOT_RECRUITING -> COMPLETED
-> TERMINATED) precede biotech binary events by weeks. Terminated
trials are especially high-signal — unannounced failures often show
here before 8-K disclosure.

Economic readthrough:
- Status -> TERMINATED -> bearish for sponsor (binary failure).
- Status -> COMPLETED (Phase 3) -> topline readout pending (60-90d).
- PRIMARY_COMPLETION_DATE imminent -> topline readout expected.
- New PHASE3 trial registered -> long-term pipeline event.

Source: https://clinicaltrials.gov/api/v2/studies (filter: INDUSTRY
sponsor + PHASE2/PHASE3 + lastUpdatePostDate 21d).

Output: clinicaltrials.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "clinicaltrials.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"


def _fetch(page_token: str | None = None) -> dict:
    d_from = (dt.date.today() - dt.timedelta(days=21)).isoformat()
    d_to = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    adv = (f"AREA[LeadSponsorClass]INDUSTRY AND "
           f"AREA[Phase](PHASE2 OR PHASE3) AND "
           f"AREA[LastUpdatePostDate]RANGE[{d_from},{d_to}]")
    params = {"filter.advanced": adv, "pageSize": 500}
    if page_token:
        params["pageToken"] = page_token
    url = ("https://clinicaltrials.gov/api/v2/studies?" +
           urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"clinicaltrials: fetch failed: {e}")
        return {}


def _row(s: dict) -> dict | None:
    ps = s.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    status = ps.get("statusModule", {})
    sponsor = ps.get("sponsorCollaboratorsModule", {})
    design = ps.get("designModule", {})
    conditions = (ps.get("conditionsModule") or {}).get("conditions", [])
    nct = ident.get("nctId") or ""
    if not nct:
        return None
    sp = sponsor.get("leadSponsor", {}).get("name", "")[:60]
    phases = design.get("phases", []) or []
    phase = "|".join(p.replace("PHASE", "P") for p in phases)
    overall = status.get("overallStatus", "")
    last_upd = (status.get("lastUpdatePostDateStruct") or {}).get("date", "")
    prim = (status.get("primaryCompletionDateStruct") or {}).get("date", "")
    comp = (status.get("completionDateStruct") or {}).get("date", "")
    cond = "|".join(conditions[:3])[:80]
    return {
        "last_update": last_upd,
        "nct": nct,
        "sponsor": sp,
        "phase": phase,
        "status": overall,
        "primary_completion": prim,
        "completion": comp,
        "title": (ident.get("briefTitle") or "")[:140],
        "condition": cond,
    }


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    token: str | None = None
    for _ in range(5):
        d = _fetch(page_token=token)
        studies = d.get("studies", []) or []
        for s in studies:
            r = _row(s)
            if r:
                rows.append(r)
        token = d.get("nextPageToken")
        if not token:
            break

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"clinicaltrials: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["last_update"], reverse=True)
    fieldnames = ["last_update", "nct", "sponsor", "phase", "status",
                  "primary_completion", "completion", "title",
                  "condition", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    statuses: dict[str, int] = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    sb = " ".join(f"{k[:7]}={v}" for k, v in sorted(statuses.items(),
                                                     key=lambda x: -x[1])[:6])
    term = [r for r in rows if r["status"] == "TERMINATED"][:3]
    term_s = " ".join(r["sponsor"][:12] for r in term)
    print(f"clinicaltrials: {len(rows)} P2/P3 industry | {sb} | "
          f"terminated={term_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
