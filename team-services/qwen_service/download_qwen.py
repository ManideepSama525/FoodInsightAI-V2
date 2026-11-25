"""Explicit, pinned Qwen3-4B snapshot download. Does not load or serve weights."""
import argparse
from pathlib import Path
from .inference.settings import DEFAULT_BASE_MODEL_ID, DEFAULT_BASE_REVISION

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parents[2] / "model_cache" / "Qwen3-4B")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    print("PINNED_MODEL:", DEFAULT_BASE_MODEL_ID)
    print("REVISION:", DEFAULT_BASE_REVISION)
    print("DESTINATION:", args.dir.resolve())
    print("DOWNLOAD_SIZE: approximately 7.5 GiB plus metadata; verify storage and access")
    result = snapshot_download(repo_id=DEFAULT_BASE_MODEL_ID, revision=DEFAULT_BASE_REVISION,
                               local_dir=str(args.dir),
                               allow_patterns=["*.json", "*.safetensors", "*.model", "*.tiktoken", "*.txt", "*.py"])
    print("SNAPSHOT:", result)
    print("MODEL_SHARDS:", len(list(args.dir.glob("model-*-of-*.safetensors"))))

if __name__ == "__main__":
    main()
