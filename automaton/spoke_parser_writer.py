"""spoke_parser_writer.py — Auto-complete the parse() stub in a freshly-generated
build_<name>.py.

After spoke_smith creates build_<name>.py with a stub `parse(body)` that returns
[], this script:

  1. Reads the spec from pending_spokes.yaml for the named spoke
  2. Fetches a small sample of upstream data using the spec's source URL
  3. Detects the format (json / csv-with-header / tsv / pipe-delimited /
     csv-zip / fixed-width-csv / unknown)
  4. Generates a parse() implementation matching the spec's output_schema
  5. Replaces the `# ── PARSE LOGIC GOES HERE ──` block in build_<name>.py
  6. Runs the spoke once to confirm the new parse() returns > 0 rows
  7. On success: leaves the spoke in_progress (audit phase will graduate it)
     On failure: writes a TODO comment block so the next cycle can pick up
     where it left off

Format-detection strategy (heuristic, not LLM):
  - JSON: response body parses with json.loads → walk for first list-of-dicts
  - CSV-w/-header: first line has > 2 commas AND looks like field names
  - TSV: same but tabs
  - Pipe: same but |
  - Fixed-width: byte position alignment detected via column-stable indices
  - csv-zip: response is application/zip → extract first .csv member
  - unknown: write fail-safe parser that returns [] and emits a clear TODO

Run:
    python3 spoke_parser_writer.py --name cftc_cot
    python3 spoke_parser_writer.py --next-in-progress
    python3 spoke_parser_writer.py --all-in-progress

Exit codes:
    0  parser written and trial run produced > 0 rows
    1  parser written but trial run still produced 0 rows (probably a
       schema-mapping issue — leaves a TODO block)
    2  upstream unreachable / sample empty
    3  spec / file IO error
"""

import argparse
import datetime as dt
import io
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
QUEUE_PATH = ROOT / "automaton" / "pending_spokes.yaml"
LOG_PATH = ROOT / "logs" / "spoke_parser_writer.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def fetch_sample(url: str, max_bytes: int = 256_000) -> tuple[bytes, str]:
    """Pull a sample of the upstream data. Returns (body, content_type)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Catalyst Edge Spoke Parser Writer)",
        "Accept": "*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            body = resp.read(max_bytes)
            return body, ctype
    except urllib.error.HTTPError as e:
        return b"", f"error:{e.code}"
    except urllib.error.URLError as e:
        return b"", f"error:{e}"
    except Exception as e:  # noqa: BLE001
        return b"", f"error:{type(e).__name__}:{e}"


def detect_format(body: bytes, ctype: str) -> str:
    """Return one of: json, csv, tsv, pipe, fixed_width, csv_zip, unknown."""
    if not body:
        return "empty"

    # zip detection
    if body[:2] == b"PK":
        return "csv_zip"

    text_head = body[:8000].decode("utf-8", errors="replace").strip()
    if not text_head:
        return "empty"

    # JSON
    if text_head[0] in "[{":
        try:
            json.loads(text_head)
            return "json"
        except Exception:
            pass

    # Try delimited
    first_line = text_head.split("\n", 1)[0]
    counts = {
        "csv": first_line.count(","),
        "tsv": first_line.count("\t"),
        "pipe": first_line.count("|"),
    }
    best = max(counts, key=counts.get)
    if counts[best] >= 2:
        return best  # csv | tsv | pipe

    # Fixed-width: lines align on consistent column starts
    lines = text_head.splitlines()[:20]
    if len(lines) >= 5:
        # If most lines have very similar length and contain multiple spaces of
        # 2+ between non-space tokens, treat as fixed-width.
        lengths = [len(l) for l in lines if l.strip()]
        if lengths and max(lengths) - min(lengths) < 10:
            multispace = sum("  " in l for l in lines)
            if multispace >= len(lines) * 0.6:
                return "fixed_width"

    return "unknown"


def parser_body_for(fmt: str, spec: dict) -> str:
    """Return Python source for parse(body) matching the detected format."""
    output_keys = list((spec.get("output_schema") or {}).keys())
    fields = spec.get("fields_required", [])

    if fmt == "json":
        return _parser_json(output_keys, fields)
    if fmt == "csv":
        return _parser_delimited(",", output_keys, fields)
    if fmt == "tsv":
        return _parser_delimited("\t", output_keys, fields)
    if fmt == "pipe":
        return _parser_delimited("|", output_keys, fields)
    if fmt == "csv_zip":
        return _parser_csv_zip(output_keys, fields)
    if fmt == "fixed_width":
        return _parser_fixed_width(output_keys, fields)
    return _parser_unknown(spec)


def _quoted_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{x}"' for x in items) + "]"


def _parser_json(output_keys: list[str], fields: list[str]) -> str:
    """Walk JSON, find first list-of-dicts, copy fields_required → output rows."""
    return f'''    rows = []
    try:
        data = json.loads(body) if isinstance(body, str) else body
        # Walk to first list-of-dicts
        candidates = []
        def _walk(node, depth=0):
            if depth > 6:
                return
            if isinstance(node, list) and node and isinstance(node[0], dict):
                candidates.append(node)
                return
            if isinstance(node, dict):
                for v in node.values():
                    _walk(v, depth + 1)
        _walk(data)
        if not candidates:
            return []
        records = max(candidates, key=len)
        wanted = {_quoted_list(fields)}
        for rec in records[:5000]:
            row = {{}}
            for k in wanted:
                if k in rec:
                    row[k] = rec[k]
            # Always carry a ticker proxy + ts so audit can correlate
            row.setdefault("ticker", rec.get("ticker") or rec.get("symbol") or "")
            row["ts"] = (rec.get("ts") or rec.get("timestamp")
                        or rec.get("date") or "")
            rows.append(row)
    except Exception as e:
        print(f"  JSON parse error: {{e}}")
    return rows
'''


def _parser_delimited(delim: str, output_keys: list[str], fields: list[str]) -> str:
    delim_repr = {",": ",", "\t": "\\t", "|": "|"}[delim]
    return f'''    rows = []
    try:
        text = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter="{delim_repr}")
        wanted = {_quoted_list(fields)}
        for rec in reader:
            row = {{}}
            for k in wanted:
                if k in rec:
                    row[k] = rec[k]
            row.setdefault("ticker", rec.get("ticker") or rec.get("symbol") or rec.get("Symbol") or "")
            row["ts"] = (rec.get("ts") or rec.get("date") or rec.get("Date") or "")
            rows.append(row)
            if len(rows) >= 5000:
                break
    except Exception as e:
        print(f"  delimited parse error: {{e}}")
    return rows
'''


def _parser_csv_zip(output_keys: list[str], fields: list[str]) -> str:
    return f'''    rows = []
    try:
        if isinstance(body, str):
            body = body.encode("utf-8", errors="replace")
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            csv_member = next((n for n in zf.namelist() if n.lower().endswith((".csv", ".txt"))), None)
            if not csv_member:
                return []
            with zf.open(csv_member) as fh:
                text = fh.read().decode("utf-8", errors="replace")
        # GDELT-style files use tabs without headers — try tab first
        sample = text.split("\\n", 1)[0]
        delim = "\\t" if sample.count("\\t") > sample.count(",") else ","
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        wanted = {_quoted_list(fields)}
        first = next(reader, None)
        if first and any(c.isalpha() for c in (first[0] or "")):
            header = first
        else:
            header = wanted or [f"col_{{i}}" for i in range(len(first or []))]
            if first:
                rec = dict(zip(header, first))
                rows.append({{k: rec.get(k, "") for k in wanted}} if wanted else rec)
        for raw in reader:
            rec = dict(zip(header, raw))
            row = {{k: rec.get(k, "") for k in wanted}} if wanted else rec
            row.setdefault("ticker", "")
            row["ts"] = rec.get("date") or rec.get("DATEADDED") or ""
            rows.append(row)
            if len(rows) >= 5000:
                break
    except Exception as e:
        print(f"  zip parse error: {{e}}")
    return rows
'''


def _parser_fixed_width(output_keys: list[str], fields: list[str]) -> str:
    """Fixed-width — split on runs of 2+ spaces, take first N tokens per line."""
    return f'''    rows = []
    try:
        text = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        lines = [l for l in text.splitlines() if l.strip()]
        if len(lines) < 2:
            return []
        # Heuristic: first line is header, subsequent lines are records.
        import re
        header = re.split(r"\\s{{2,}}", lines[0].strip())
        wanted = {_quoted_list(fields)} or header
        for line in lines[1:]:
            tokens = re.split(r"\\s{{2,}}", line.strip())
            rec = dict(zip(header, tokens))
            row = {{}}
            for k in wanted:
                if k in rec:
                    row[k] = rec[k]
            row.setdefault("ticker", rec.get(header[0], "") if header else "")
            row["ts"] = ""
            rows.append(row)
            if len(rows) >= 5000:
                break
    except Exception as e:
        print(f"  fixed-width parse error: {{e}}")
    return rows
'''


def _parser_unknown(spec: dict) -> str:
    name = spec.get("name", "")
    src_url = (spec.get("source") or {}).get("url", "")
    fields = spec.get("fields_required", [])
    schema = spec.get("output_schema", {})
    return f'''    rows = []
    # TODO: parser_writer could not auto-detect format for {name!r}.
    # Spec source: {src_url}
    # Spec required fields: {fields}
    # Spec output schema: {schema}
    #
    # Action: LLM fallback (llm_parser_writer.py) will be invoked next.
    # If both heuristic and LLM fail, manually write a parser that returns
    # list[dict] with the schema above, then run:
    #   python3 /home/operator/.openclaw/workspace/automaton/spoke_audit.py --name {name}
    return rows
'''


PARSER_REGION_RE = re.compile(
    r"(    rows = \[\][\s\S]*?return rows\n)",
    re.MULTILINE,
)
PARSER_HEADER_REGION_RE = re.compile(
    r"(def parse\(body\):\s*\n)(\s*\"\"\"[\s\S]*?\"\"\"\s*\n)?",
    re.MULTILINE,
)


def install_parser(file_path: Path, parser_src: str, fmt: str) -> bool:
    """Replace the parse() body in build_<name>.py with our generated source."""
    text = file_path.read_text(encoding="utf-8")
    # Ensure necessary stdlib imports are present
    needed = []
    if "import io" not in text:
        needed.append("import io")
    if "import zipfile" not in text and "csv_zip" in fmt:
        needed.append("import zipfile")
    if needed:
        # Insert after the existing 'import csv' line if possible
        text = re.sub(
            r"(import csv\n)",
            "\\1" + "\n".join(needed) + "\n",
            text, count=1)

    # Wrap parser_src so it's the body of parse(body) — the def + docstring
    # already exist in the template. We replace from the first `    rows = []`
    # to and including `    return rows`.
    new_text, n = PARSER_REGION_RE.subn(parser_src, text, count=1)
    if n == 0:
        log(f"  WARN: parser region marker not found in {file_path.name}")
        return False
    file_path.write_text(new_text, encoding="utf-8")
    return True


def trial_run(name: str) -> tuple[bool, int, str]:
    """Run build_<name>.py and report (rc==0, row_count_in_csv, tail)."""
    script = ROOT / f"build_{name}.py"
    csv_path = ROOT / f"{name}.csv"
    try:
        result = subprocess.run(
            ["python3", str(script)],
            capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return False, 0, "timeout"
    rc_ok = result.returncode == 0
    rows = 0
    if csv_path.exists():
        with csv_path.open() as fh:
            for i, _ in enumerate(fh):
                rows = i  # excludes header
    return rc_ok, rows, (result.stdout + result.stderr)[-300:]


def write_one(spec: dict) -> int:
    name = spec["name"]
    log(f"=== parser_writer: {name} ===")
    file_path = ROOT / f"build_{name}.py"
    if not file_path.exists():
        log(f"  ABORT: {file_path} missing — run spoke_smith first")
        return 3

    url = spec.get("source", {}).get("url", "")
    if not url:
        log("  ABORT: spec has no source URL")
        return 3

    log(f"  fetching sample from {url}")
    body, ctype = fetch_sample(url)
    if not body:
        log(f"  upstream unreachable: ctype={ctype}")
        return 2

    fmt = detect_format(body, ctype)
    log(f"  detected format: {fmt}  ({len(body)} bytes, ctype={ctype!r})")

    parser_src = parser_body_for(fmt, spec)
    if not install_parser(file_path, parser_src, fmt):
        log("  parser install failed")
        return 3
    log(f"  installed heuristic parser into {file_path.name}")

    ok, row_count, tail = trial_run(name)
    log(f"  trial run (heuristic): rc_ok={ok}  rows={row_count}  tail={tail[-120:]!r}")
    if ok and row_count > 0:
        log(f"PASS: {name} now produces {row_count} rows (heuristic)")
        return 0

    # Heuristic produced 0 rows OR format was unknown. Escalate to LLM.
    log(f"  heuristic insufficient (fmt={fmt}, rows={row_count}) — escalating to LLM")
    try:
        sys.path.insert(0, str(ROOT / "automaton"))
        from llm_parser_writer import generate_parser  # type: ignore
    except ImportError as e:
        log(f"  LLM fallback unavailable: {e}")
        return 1

    llm_parser, provider = generate_parser(spec, body)
    if llm_parser is None:
        log(f"  LLM fallback FAILED: {provider}")
        log(f"  leaving spoke in_progress with heuristic parser; manual review needed")
        return 1

    log(f"  LLM ({provider}) returned a candidate parser ({len(llm_parser)} chars)")
    if not install_parser(file_path, llm_parser, "llm:" + provider):
        log("  LLM parser install failed (region marker not found)")
        return 1

    ok2, row_count2, tail2 = trial_run(name)
    log(f"  trial run (LLM): rc_ok={ok2}  rows={row_count2}  tail={tail2[-120:]!r}")
    if ok2 and row_count2 > 0:
        log(f"PASS: {name} now produces {row_count2} rows (via LLM:{provider})")
        return 0
    log(f"PARTIAL: LLM parser also returned 0 rows — leaving for manual review")
    return 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--name", help="run on a specific spoke")
    p.add_argument("--next-in-progress", action="store_true")
    p.add_argument("--all-in-progress", action="store_true")
    args = p.parse_args()

    state = load_yaml(QUEUE_PATH)
    spokes = state.get("spokes", [])

    targets: list[dict] = []
    if args.name:
        s = next((x for x in spokes if x.get("name") == args.name), None)
        if not s:
            log(f"--name {args.name} not in queue")
            return 3
        targets = [s]
    elif args.all_in_progress:
        targets = [s for s in spokes if s.get("state") == "in_progress"]
    elif args.next_in_progress:
        targets = [s for s in spokes if s.get("state") == "in_progress"][:1]
    else:
        log("pick --name, --next-in-progress, or --all-in-progress")
        return 3

    if not targets:
        log("no in_progress spokes")
        return 1

    worst = 0
    for t in targets:
        rc = write_one(t)
        worst = max(worst, rc)
    return worst


if __name__ == "__main__":
    sys.exit(main())
