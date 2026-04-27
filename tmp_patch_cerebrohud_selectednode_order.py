from pathlib import Path


path = Path("/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx")
text = path.read_text(encoding="utf-8")

anchor = """  useEffect(() => {\n    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)\n  }, [rawNodes.length > 0])   // fire once nodes are loaded\n\n  // ── Target marker: build/destroy on selection change ─────────────────────\n"""
insert = """  useEffect(() => {\n    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)\n  }, [rawNodes.length > 0])   // fire once nodes are loaded\n\n  const selectedNode = useMemo(() => {\n    if (!selectedTicker) return null\n    return nodeMapRef.current[selectedTicker] || rawNodes.find(n => n.id === selectedTicker) || null\n  }, [rawNodes, selectedTicker])\n\n  // ── Target marker: build/destroy on selection change ─────────────────────\n"""
if anchor not in text:
    raise SystemExit("selectedNode insert anchor not found")
text = text.replace(anchor, insert, 1)

old = """  const selectedNode = useMemo(() => {\n    if (!selectedTicker) return null\n    return nodeMapRef.current[selectedTicker] || rawNodes.find(n => n.id === selectedTicker) || null\n  }, [rawNodes, selectedTicker])\n\n"""
count = text.count(old)
if count < 2:
    raise SystemExit(f"expected moved selectedNode block twice after insert, found {count}")
text = text.replace(old, "", 1)

path.write_text(text, encoding="utf-8")
