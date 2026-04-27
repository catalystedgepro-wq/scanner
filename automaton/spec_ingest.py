"""spec_ingest.py — Append YAML spec stanzas to pending_spokes.yaml.

The weekly spec-author agent emails you paste-ready YAML. This script ingests
those stanzas safely:
  - Parses the input
  - Validates each spec (required keys, name pattern, no collisions)
  - Backs up pending_spokes.yaml
  - Appends valid specs as `state: queued`
  - Prints a per-spec PASS/SKIP/REJECT report

THREE WAYS TO PASTE (all idempotent — duplicates are skipped):

  1) Pipe from clipboard (Linux/WSL with xclip):
        xclip -o | python3 /home/operator/.openclaw/workspace/automaton/spec_ingest.py

  2) Heredoc (paste between the markers):
        python3 /home/operator/.openclaw/workspace/automaton/spec_ingest.py <<'EOF'
          - name: foo
            title: "Foo Source"
            ...
        EOF

  3) From a file (save the email body to /tmp/inbox.yaml first):
        python3 /home/operator/.openclaw/workspace/automaton/spec_ingest.py /tmp/inbox.yaml

The script accepts:
  - Bare list of stanzas (the agent's email body, between the --- markers)
  - A full document with `spokes:` at the top level
  - Mixed content with extra prose around the YAML — it extracts the YAML block

Exit codes:
  0  appended N specs (could be 0 if all duplicates)
  1  YAML parse error or no stanzas detected
  2  validation rejected ALL stanzas
  3  IO error
"""

import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
QUEUE_PATH = ROOT / "automaton" / "pending_spokes.yaml"
BACKUP_DIR = ROOT / "automaton" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def load_input() -> str:
    """Accept stdin OR a single file-path argument."""
    if len(sys.argv) > 1 and sys.argv[1] not in ("-", ""):
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"ERROR: input file not found: {path}", file=sys.stderr)
            sys.exit(3)
        return path.read_text(encoding="utf-8")
    return sys.stdin.read()


def extract_yaml_block(text: str) -> str:
    """Strip prose around the YAML; the agent email wraps stanzas in markers."""
    # Look for fenced markers first
    m = re.search(r"---\s*YAML\s*stanzas\s*---\s*\n(.*?)\n---\s*end\s*---",
                  text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    # Look for triple-backtick yaml fences
    m = re.search(r"```(?:yaml|yml)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Otherwise look for the first `- name:` line and take everything from there
    m = re.search(r"((?:^|\n)\s*-\s*name:\s.*)$", text, re.DOTALL)
    if m:
        return m.group(1)
    return text


def parse_yaml(text: str) -> list[dict]:
    """Return a list of spec dicts, regardless of input form."""
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML required. Install: pip install --user pyyaml",
              file=sys.stderr)
        sys.exit(3)

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    if parsed is None:
        return []
    if isinstance(parsed, dict) and "spokes" in parsed:
        return list(parsed.get("spokes") or [])
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and parsed.get("name"):
        return [parsed]
    return []


_NAME_RE = re.compile(r"^[a-z][a-z0-9_]+$")


def validate_spec(spec: dict, existing_names: set) -> tuple[bool, str]:
    name = spec.get("name", "")
    if not _NAME_RE.match(name):
        return False, f"name must match ^[a-z][a-z0-9_]+$ (got {name!r})"
    if name in existing_names:
        return False, f"duplicate name (already in queue or shipped)"
    src = spec.get("source") or {}
    if not isinstance(src, dict) or not src.get("url"):
        return False, "missing source.url"
    if not str(src["url"]).startswith(("http://", "https://")):
        return False, f"source.url must start with http(s):// (got {src['url']!r})"
    if not spec.get("fields_required"):
        return False, "missing fields_required (list)"
    if not spec.get("output_schema"):
        return False, "missing output_schema (dict)"
    return True, "ok"


def normalize(spec: dict) -> dict:
    """Force state=queued and add tracking fields."""
    spec = dict(spec)  # copy
    spec["state"] = "queued"
    spec["last_transition_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    spec.setdefault("priority", 99)
    spec.setdefault("title", spec["name"])
    spec.setdefault("expected_alpha_lift", 0)
    return spec


def main() -> int:
    raw = load_input()
    if not raw.strip():
        print("ERROR: empty input. Pipe YAML in, pass a file path, or use a heredoc.",
              file=sys.stderr)
        print(__doc__.split('\n\nTHREE WAYS')[1].split('\n\nThe script')[0],
              file=sys.stderr)
        return 1

    yaml_text = extract_yaml_block(raw)
    incoming = parse_yaml(yaml_text)
    if not incoming:
        print("ERROR: no spec stanzas found in input", file=sys.stderr)
        print("Make sure your paste includes lines starting with `- name:`",
              file=sys.stderr)
        return 1

    print(f"📥 Found {len(incoming)} candidate spec(s) in input")

    # Load existing queue
    if not QUEUE_PATH.exists():
        print(f"ERROR: queue file missing: {QUEUE_PATH}", file=sys.stderr)
        return 3

    import yaml  # already validated
    state = yaml.safe_load(QUEUE_PATH.read_text(encoding="utf-8")) or {}
    state.setdefault("spokes", [])
    existing_names = {s.get("name") for s in state["spokes"] if s.get("name")}
    existing_names |= set(state.get("shipped", []))

    # Backup before mutation
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup = BACKUP_DIR / f"pending_spokes.{ts}.yaml"
    shutil.copy2(QUEUE_PATH, backup)
    print(f"📦 Backed up queue to {backup.name}")

    appended, skipped, rejected = 0, 0, 0
    print()
    for i, spec in enumerate(incoming, 1):
        name = spec.get("name", f"<row {i}>")
        ok, reason = validate_spec(spec, existing_names)
        if not ok:
            if "duplicate" in reason:
                print(f"  ⊘ SKIP   {name:25s}  {reason}")
                skipped += 1
            else:
                print(f"  ✗ REJECT {name:25s}  {reason}")
                rejected += 1
            continue
        normalized = normalize(spec)
        state["spokes"].append(normalized)
        existing_names.add(name)
        print(f"  ✓ ADD    {name:25s}  priority={normalized.get('priority')}")
        appended += 1

    if appended == 0:
        print()
        print(f"⚠️  No new specs appended (skipped={skipped}, rejected={rejected})")
        return 2 if rejected and not skipped else 0

    # Write back
    state["last_ingest_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    QUEUE_PATH.write_text(
        yaml.safe_dump(state, sort_keys=False, default_flow_style=False),
        encoding="utf-8")

    print()
    print(f"✅ Ingested {appended} new spec(s) into pending_spokes.yaml")
    if skipped or rejected:
        print(f"   (skipped {skipped} duplicates, rejected {rejected} invalid)")
    print(f"   Next biweekly automaton_loop fire: Sunday 14:00 UTC")
    print(f"   Inspect queue: cat {QUEUE_PATH}")
    print(f"   Roll back:     cp {backup} {QUEUE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
