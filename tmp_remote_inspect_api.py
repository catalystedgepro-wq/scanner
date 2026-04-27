from pathlib import Path


path = Path("/opt/catalyst/api_server.py")
text = path.read_text(encoding="utf-8")

print("has_model_metadata=", "model_metadata" in text)
print("model_metadata_count=", text.count("model_metadata"))
print("has_model_selection_env=", "ANTHROPIC_MODEL_FAST" in text and "ANTHROPIC_MODEL_SMART" in text)
