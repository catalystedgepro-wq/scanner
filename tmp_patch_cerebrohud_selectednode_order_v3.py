from pathlib import Path


path = Path("/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx")
text = path.read_text(encoding="utf-8")

insert_anchor = """  // ── Target marker: build/destroy on selection change ─────────────────────\n"""
selected_block = """  const selectedNode = useMemo(() => {\n    if (!selectedTicker) return null\n    return nodeMapRef.current[selectedTicker] || rawNodes.find(n => n.id === selectedTicker) || null\n  }, [rawNodes, selectedTicker])\n\n"""

if insert_anchor not in text:
    raise SystemExit("target marker anchor not found")
if text.count(selected_block) != 1:
    raise SystemExit(f"expected one selectedNode block before move, found {text.count(selected_block)}")

text = text.replace(insert_anchor, selected_block + insert_anchor, 1)

before, match, after = text.rpartition(selected_block)
if not match:
    raise SystemExit("could not locate trailing selectedNode block")
text = before + after

if text.count(selected_block) != 1:
    raise SystemExit(f"expected one selectedNode block after move, found {text.count(selected_block)}")

path.write_text(text, encoding="utf-8")
