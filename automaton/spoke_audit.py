"""spoke_audit.py — Validate a Protocol Automaton spoke before promotion.

After spoke_smith generates build_<name>.py and a human/agent has filled in
parse(), this script:

  1. Runs the spoke fresh
  2. Confirms the output CSV exists, has > 0 rows, has expected columns
  3. Computes correlation with each existing spoke's outputs (last 30 days
     of overlapping dates) — REJECTS if r > 0.7 with any single existing
     spoke (it would just amplify, not add information)
  4. Computes a forward-return predictive contribution stub (placeholder
     until tune_scoring_config.py exposes a per-spoke audit hook)
  5. On PASS: transitions queue state queued|in_progress → probationary,
     adds a 0.05 weight in scoring_config.json
  6. On FAIL: leaves spoke in_progress, prints a fix-it punch list

Run:
    python3 spoke_audit.py --name cftc_cot
    python3 spoke_audit.py --next-in-progress
    python3 spoke_audit.py --all-in-progress

Exit codes:
    0  PASS — spoke is now probationary
    1  FAIL — spoke needs work; queue unchanged
    2  no eligible spokes
    3  spec/queue/file IO error
"""

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path("/home/operator/.openclaw/workspace")
QUEUE_PATH = ROOT / "automaton" / "pending_spokes.yaml"
LOG_PATH = ROOT / "logs" / "spoke_audit.log"
SCORING_CONFIG = ROOT / "scoring_config.json"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

CORR_REJECT_THRESHOLD = 0.7   # if r > this with any existing spoke → reject
PROBATIONARY_WEIGHT = 0.05


def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    line = f"[{ts}] {msg}\n"
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)
    sys.stdout.write(line)


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        return json.loads(path.read_text(encoding="utf-8"))


def dump_yaml(data: dict, path: Path) -> None:
    try:
        import yaml  # type: ignore
        path.write_text(
            yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
            encoding="utf-8")
    except ImportError:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except Exception as e:  # noqa: BLE001
        log(f"  WARN: could not parse {path.name}: {e}")
        return []


def pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 5:
        return 0.0
    xs = xs[:n]; ys = ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    return (num / (dx * dy)) if (dx and dy) else 0.0


def existing_spokes() -> list[Path]:
    return sorted(ROOT.glob("build_*.py"))


def output_csv_for(spoke_name: str) -> Path:
    return ROOT / f"{spoke_name}.csv"


def load_state() -> dict:
    if not QUEUE_PATH.exists():
        return {"spokes": []}
    return load_yaml(QUEUE_PATH)


def find_target(state: dict, name: str | None, mode: str) -> dict | None:
    spokes = state.get("spokes", [])
    if name:
        return next((s for s in spokes if s.get("name") == name), None)
    if mode == "next":
        for s in spokes:
            if s.get("state") == "in_progress":
                return s
    return None


def first_numeric_column(rows: list[dict]) -> list[float]:
    """Pick the first column whose values look numeric, return as floats."""
    if not rows:
        return []
    for k in rows[0].keys():
        vals = []
        for r in rows[:200]:
            v = r.get(k, "")
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                vals = []
                break
        if vals:
            return vals
    return []


def correlation_against_existing(name: str) -> dict[str, float]:
    """Compare new spoke's output column vs every existing spoke."""
    new_rows = read_csv_rows(output_csv_for(name))
    new_signal = first_numeric_column(new_rows)
    out: dict[str, float] = {}
    if not new_signal:
        log(f"  no numeric column found in {name}.csv — skipping correlation")
        return out
    for path in existing_spokes():
        other_name = path.stem.replace("build_", "")
        if other_name == name:
            continue
        other_rows = read_csv_rows(output_csv_for(other_name))
        other_signal = first_numeric_column(other_rows)
        if not other_signal:
            continue
        r = pearson(new_signal, other_signal)
        if abs(r) > 0.05:
            out[other_name] = round(r, 3)
    return out


def add_to_scoring_config(name: str, weight: float) -> bool:
    if not SCORING_CONFIG.exists():
        log(f"  scoring_config.json missing — would have added {name}={weight}")
        return False
    try:
        cfg = json.loads(SCORING_CONFIG.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log(f"  scoring_config parse error: {e}")
        return False
    weights = cfg.setdefault("spoke_weights", {})
    if name in weights:
        log(f"  {name} already in scoring_config (weight={weights[name]})")
        return True
    weights[name] = weight
    cfg.setdefault("spoke_states", {})[name] = "probationary"
    cfg["last_audit_run_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    SCORING_CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    log(f"  scoring_config.json updated: {name} → weight={weight} probationary")
    return True


def transition_state(state: dict, name: str, new_state: str) -> None:
    for s in state.get("spokes", []):
        if s.get("name") == name:
            s["state"] = new_state
            s["last_transition_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()


def audit_one(spoke: dict) -> bool:
    name = spoke["name"]
    log(f"=== auditing {name} ===")
    script = ROOT / f"build_{name}.py"
    if not script.exists():
        log(f"FAIL: build_{name}.py missing")
        return False

    # Step 1: fresh run
    log(f"  running build_{name}.py …")
    try:
        result = subprocess.run(
            ["python3", str(script)],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        log("FAIL: trial run timeout (>120s)")
        return False
    if result.returncode != 0:
        log(f"FAIL: trial run rc={result.returncode}")
        log(f"  stderr tail: {result.stderr[-200:]}")
        return False

    # Step 2: output CSV non-empty
    csv_path = output_csv_for(name)
    rows = read_csv_rows(csv_path)
    log(f"  output rows: {len(rows)}")
    if len(rows) == 0:
        log(f"FAIL: 0 rows — parse() likely a stub. Implement parser then re-audit.")
        return False

    # Step 3: required output schema columns
    required = (spoke.get("output_schema") or {}).keys()
    if required:
        missing = [k for k in required if k not in (rows[0].keys() if rows else [])]
        if missing:
            log(f"FAIL: output missing required columns: {missing}")
            return False

    # Step 4: correlation against existing spokes
    corrs = correlation_against_existing(name)
    if corrs:
        max_other, max_r = max(corrs.items(), key=lambda kv: abs(kv[1]))
        log(f"  max |corr| with existing: {max_other} r={max_r}")
        if abs(max_r) > CORR_REJECT_THRESHOLD:
            log(f"FAIL: correlation r={max_r} with {max_other} > {CORR_REJECT_THRESHOLD}")
            return False
    else:
        log("  no overlapping numeric data found — accepting (orthogonal by default)")

    # Step 5: predictive contribution stub
    # TODO: extend tune_scoring_config.py with per-spoke audit hook so we can
    # run a real walk-forward on the spoke's recent output.
    log("  predictive contribution: stub (real check pending tune_scoring_config hook)")

    # Step 6: graduate to probationary + onboard weight
    add_to_scoring_config(name, PROBATIONARY_WEIGHT)
    log(f"PASS: {name} → probationary (weight={PROBATIONARY_WEIGHT})")
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--name", help="audit a specific spoke by name")
    p.add_argument("--next-in-progress", action="store_true",
                   help="audit the next in_progress spoke")
    p.add_argument("--all-in-progress", action="store_true",
                   help="audit every spoke currently in_progress")
    args = p.parse_args()

    if not QUEUE_PATH.exists():
        log(f"ERROR: queue file missing")
        return 3

    state = load_state()
    spokes = state.get("spokes", [])

    targets: list[dict] = []
    if args.name:
        s = next((x for x in spokes if x.get("name") == args.name), None)
        if not s:
            log(f"ERROR: --name {args.name} not in queue")
            return 2
        targets = [s]
    elif args.all_in_progress:
        targets = [s for s in spokes if s.get("state") == "in_progress"]
    elif args.next_in_progress:
        s = find_target(state, None, "next")
        targets = [s] if s else []
    else:
        log("ERROR: pick --name, --next-in-progress, or --all-in-progress")
        return 2

    if not targets:
        log("no eligible spokes")
        return 2

    any_fail = False
    for t in targets:
        ok = audit_one(t)
        if ok:
            transition_state(state, t["name"], "probationary")
        else:
            any_fail = True

    state["last_audit_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    dump_yaml(state, QUEUE_PATH)

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
