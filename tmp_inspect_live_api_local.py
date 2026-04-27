from pathlib import Path


text = Path("/home/operator/.openclaw/workspace/tmp_live_api_server.py").read_text(encoding="utf-8")
print("has_model_metadata", "model_metadata" in text)
print("model_metadata_count", text.count("model_metadata"))
print("has_fast_env", "ANTHROPIC_MODEL_FAST" in text)
print("has_smart_env", "ANTHROPIC_MODEL_SMART" in text)
