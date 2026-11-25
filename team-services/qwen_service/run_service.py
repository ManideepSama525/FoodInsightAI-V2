"""Portable base-Qwen service launcher for FoodInsightAI team demos.

Place team-services/ at the root of a fresh FoodInsightAI-V2 checkout.
Preflight: py -3.12 team-services/qwen_service/run_service.py --check
Serve:     py -3.12 team-services/qwen_service/run_service.py --serve
"""
from __future__ import annotations
import argparse
import importlib.metadata
import os
import secrets
import subprocess
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
SERVICES_ROOT = SERVICE_DIR.parent
ROOT = SERVICES_ROOT.parent
BASE = Path(os.environ.get("RECIPE_BASE_MODEL_LOCAL", str(ROOT / "model_cache" / "Qwen3-4B"))).expanduser()
TOKEN_PATH = Path(os.environ.get("RECIPE_SERVICE_TOKEN_FILE", str(Path.home() / ".foodinsightai" / "recipe_service_token.txt"))).expanduser()

def _python():
    custom = os.environ.get("FOODINSIGHT_QWEN_PYTHON", "").strip()
    candidates = [Path(custom)] if custom else [
        SERVICES_ROOT / ".qwen-venv" / "Scripts" / "python.exe",
        ROOT / "recipe-inference-lab" / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(sys.executable)

def _check():
    required = [
        BASE / "config.json",
        SERVICE_DIR / "base_service.py",
        SERVICE_DIR / "inference" / "generator.py",
        SERVICE_DIR / "inference" / "settings.py",
        SERVICE_DIR / "inference" / "model_loader.py",
        SERVICE_DIR / "inference" / "prompts.py",
    ]
    absent = [str(p) for p in required if not p.is_file()]
    shards = sorted(BASE.glob("model-*-of-*.safetensors")) if BASE.is_dir() else []
    if len(shards) != 3:
        absent.append("Expected 3 model shards under " + str(BASE))
    if absent:
        raise RuntimeError("Missing Qwen requirements:\n  " + "\n  ".join(absent))
    python = _python()
    test = subprocess.run([str(python), "-c", "import torch, fastapi, uvicorn, transformers, accelerate, bitsandbytes, peft"],
                          capture_output=True, text=True)
    if test.returncode:
        raise RuntimeError("Qwen Python environment missing packages or incompatible: " + str(python) +
                           "\n" + test.stderr[-1200:])
    gpu = subprocess.run([str(python), "-c", "import torch; print(torch.cuda.is_available())"],
                         capture_output=True, text=True)
    if gpu.returncode or gpu.stdout.strip() != "True":
        raise RuntimeError("CUDA GPU unavailable in the selected Qwen Python environment. "
                           "Use an RTX-compatible PyTorch build.")
    print("QWEN_MODEL: 3 SHARDS PRESENT")
    print("QWEN_PYTHON:", python)
    print("GPU_CUDA: AVAILABLE")
    print("TOKEN_FILE:", TOKEN_PATH)
    return python

def _token():
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(token) < 32:
            raise RuntimeError("Existing token too short, refusing to replace it")
        return token
    token = secrets.token_urlsafe(48)
    with TOKEN_PATH.open("x", encoding="utf-8") as f:
        f.write(token)
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass
    return token

def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--serve", action="store_true")
    parser.add_argument("--bind", default="127.0.0.1", help="Local bind address (default 127.0.0.1)")
    parser.add_argument("--allow-nonlocal-bind", action="store_true")
    args = parser.parse_args()
    python = _check()
    if args.check:
        print("STATUS: PREFLIGHT_PASSED")
        return
    if args.bind not in {"127.0.0.1", "localhost", "::1"} and not args.allow_nonlocal_bind:
        raise RuntimeError("Non-loopback binding requires --allow-nonlocal-bind; restrict firewall/LAN access")
    env = os.environ.copy()
    env.update({
        "RECIPE_BASE_MODEL_LOCAL": str(BASE),
        "RECIPE_LOAD_IN_4BIT": "true",
        "RECIPE_COMPUTE_DTYPE": "float16",
        "RECIPE_ENABLE_THINKING": "false",
        "RECIPE_ADAPTER_PATH": "",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "RECIPE_SERVICE_TOKEN": _token(),
        "PYTHONPATH": str(SERVICES_ROOT) + os.pathsep + env.get("PYTHONPATH", ""),
    })
    print("URL: http://" + args.bind + ":8023")
    print("TOKEN_FILE:", TOKEN_PATH, "(private, token not printed)")
    print("NOTE: Docker host.docker.internal connectivity requires an explicit test")
    subprocess.run([str(python), "-m", "uvicorn", "qwen_service.base_service:app",
                    "--host", args.bind, "--port", "8023"], env=env, cwd=SERVICES_ROOT, check=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("SERVICE_STOPPED")
    except Exception as exc:
        print("STATUS: FAILED", type(exc).__name__, exc)
        sys.exit(1)
