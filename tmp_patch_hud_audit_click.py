from pathlib import Path


path = Path("/home/operator/.openclaw/workspace/tmp_hud_visual_audit.mjs")
text = path.read_text(encoding="utf-8")

old = """  await page.goto(`http://127.0.0.1:${port}`, { waitUntil: 'domcontentloaded' });\n  await page.waitForTimeout(9000);\n"""
new = """  await page.goto(`http://127.0.0.1:${port}`, { waitUntil: 'domcontentloaded' });\n  const launchButton = page.getByRole('button', { name: /launch hud/i });\n  if (await launchButton.count()) {\n    await launchButton.click();\n  }\n  await page.waitForTimeout(9000);\n"""
if old not in text:
    raise SystemExit("audit navigation block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
