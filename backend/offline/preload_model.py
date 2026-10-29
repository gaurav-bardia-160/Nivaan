"""Preload and warm up local LLM into RAM/VRAM with indefinite keep_alive."""
import os
import sys
import time
import requests

DEFAULT_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:3b")
BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")

def preload(model: str = DEFAULT_MODEL, base_url: str = BASE_URL) -> bool:
    print(f"[INFO] Connecting to Ollama server at {base_url}...")
    # Verify server is listening
    connected = False
    for attempt in range(12):
        try:
            r = requests.get(f"{base_url}/api/tags", timeout=1.5)
            if r.status_code == 200:
                connected = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not connected:
        print(f"[WARNING] Could not connect to Ollama server at {base_url}. Model preloading skipped.")
        return False

    # Check available models
    try:
        tags_data = requests.get(f"{base_url}/api/tags", timeout=3).json()
        available = [m.get("name") for m in tags_data.get("models", [])]
        matched_model = None
        for m in available:
            if m == model or m.startswith(f"{model}:") or model.startswith(f"{m}:"):
                matched_model = m
                break
        if not matched_model and available:
            matched_model = available[0]
            print(f"[INFO] Target '{model}' not found; using available model '{matched_model}'.")
        elif not matched_model:
            matched_model = model
    except Exception:
        matched_model = model

    print(f"[INFO] Loading model '{matched_model}' into RAM (keep_alive: forever)...")
    try:
        t0 = time.time()
        # keep_alive: -1 instructs Ollama to keep the weights loaded indefinitely
        res = requests.post(
            f"{base_url}/api/generate",
            json={"model": matched_model, "keep_alive": -1},
            timeout=90
        )
        duration = time.time() - t0
        if res.status_code == 200:
            # Query /api/ps to confirm resident model
            ps_res = requests.get(f"{base_url}/api/ps", timeout=5).json()
            active_models = ps_res.get("models", [])
            for am in active_models:
                ram_gb = round(am.get("size", 0) / (1024 ** 3), 2)
                details = am.get("details", {})
                params = details.get("parameter_size", "3B")
                print(f"[INFO] Model '{am.get('name')}' ({params}, {ram_gb} GB) is loaded in RAM in {duration:.1f}s.")
                return True
            print(f"[INFO] Model '{matched_model}' warmup completed in {duration:.1f}s (Status: {res.status_code}).")
            return True
        else:
            print(f"[WARNING] Preload returned HTTP {res.status_code}: {res.text[:100]}")
            return False
    except Exception as exc:
        print(f"[WARNING] Preload error: {exc}")
        return False

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    success = preload(target)
    sys.exit(0 if success else 1)
