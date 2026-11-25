"""Runtime settings for the standalone recipe-generation inference service.

Every value can be overridden with an environment variable so that the same
code runs against:

* the original local model cache (``model_cache/Qwen3-4B``),
* the portable ``recsi/model`` adapter that ships separately,
* a Hugging Face repo id resolved at container start-up,

without editing source.

The defaults below reproduce the *actual* environment used by the original
project (see ``documentation/EXISTING_SYSTEM_ARCHITECTURE.md``):

* base model      ``Qwen/Qwen3-4B`` (Apache-2.0)
* base revision   ``1cfa9a7208912126459214e8b04321603b3df60c``
* adapter         PEFT LoRA, r=16, alpha=32, task_type=CAUSAL_LM
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Base model identity (do NOT substitute another Qwen variant)
# --------------------------------------------------------------------------- #
DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3-4B"
DEFAULT_BASE_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def package_root() -> Path:
    """Return the directory that contains the ``inference/`` package."""
    return Path(__file__).resolve().parents[1]


def _resolve_adapter_dir() -> Path | None:
    """Find the LoRA adapter directory.

    Search order:
      1. ``RECIPE_ADAPTER_PATH`` (explicit, wins if it exists)
      2. ``<package_root>/recsi/model``   (this package + recsi.zip layout)
      3. ``<package_root>/model``         (standalone extraction)
      4. ``<package_root>/../recsi/model`` (package nested inside a repo)
    Returns ``None`` when nothing is found so callers can raise a clear error.
    """
    explicit = _env("RECIPE_ADAPTER_PATH")
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.exists() else candidate

    root = package_root()
    candidates = [
        root / "recsi" / "model",
        root / "model",
        root.parent / "recsi" / "model",
    ]
    for candidate in candidates:
        if (candidate / "adapter_config.json").is_file():
            return candidate
    return None


@dataclass(frozen=True)
class InferenceSettings:
    """Immutable settings snapshot, built once per process."""

    base_model_id: str
    base_revision: str
    base_model_local: str | None
    adapter_path: str | None

    load_in_4bit: bool
    bnb_quant_type: str
    bnb_double_quant: bool
    compute_dtype: str

    device_map: str
    max_new_tokens: int
    do_sample: bool
    repetition_penalty: float
    enable_thinking: bool

    def adapter_dir(self) -> Path | None:
        return Path(self.adapter_path) if self.adapter_path else None

    def uses_local_base(self) -> bool:
        return bool(self.base_model_local)

    def describe(self) -> dict:
        """Safe-to-log summary (no secrets, no absolute personal paths)."""
        return {
            "base_model_id": self.base_model_id,
            "base_revision": self.base_revision,
            "base_model_local": bool(self.base_model_local),
            "adapter_path": self.adapter_path,
            "load_in_4bit": self.load_in_4bit,
            "bnb_quant_type": self.bnb_quant_type,
            "bnb_double_quant": self.bnb_double_quant,
            "compute_dtype": self.compute_dtype,
            "device_map": self.device_map,
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.do_sample,
        }


def get_settings() -> InferenceSettings:
    """Build settings from the environment (call once at start-up)."""
    adapter = _resolve_adapter_dir()
    return InferenceSettings(
        base_model_id=_env("RECIPE_BASE_MODEL", DEFAULT_BASE_MODEL_ID),
        base_revision=_env("RECIPE_BASE_REVISION", DEFAULT_BASE_REVISION),
        base_model_local=_env("RECIPE_BASE_MODEL_LOCAL"),
        adapter_path=str(adapter) if adapter else _env("RECIPE_ADAPTER_PATH"),
        load_in_4bit=_env_bool("RECIPE_LOAD_IN_4BIT", True),
        bnb_quant_type=_env("RECIPE_BNB_QUANT_TYPE", "nf4"),
        bnb_double_quant=_env_bool("RECIPE_BNB_DOUBLE_QUANT", True),
        compute_dtype=_env("RECIPE_COMPUTE_DTYPE", "bfloat16"),
        device_map=_env("RECIPE_DEVICE_MAP", "auto"),
        max_new_tokens=_env_int("RECIPE_MAX_NEW_TOKENS", 256),
        do_sample=_env_bool("RECIPE_DO_SAMPLE", False),
        repetition_penalty=_env_float("RECIPE_REPETITION_PENALTY", 1.05),
        enable_thinking=_env_bool("RECIPE_ENABLE_THINKING", False),
    )
