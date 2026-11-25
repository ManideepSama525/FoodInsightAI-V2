"""Model + tokenizer loading for recipe generation.

This is the **missing piece** in the original project: the deployed backend
(``backend/models/qwen_text.py``) loads the *base* Qwen3-4B only, and the only
place that ever attached the LoRA adapter was ``training/evaluate.py``
(``PeftModel.from_pretrained``). This module reproduces that working path in a
form that can be served, with:

* base model either local (``RECIPE_BASE_MODEL_LOCAL``) or from the Hub with a
  pinned revision (``RECIPE_BASE_MODEL`` + ``RECIPE_BASE_REVISION``);
* optional 4-bit NF4 quantization via bitsandbytes (auto-disabled on CPU);
* lazy, thread-safe, single-load caching;
* a readiness probe used by ``/ready``.

The adapter is attached with ``PeftModel.from_pretrained(model, adapter_dir)``
exactly as ``evaluate.py`` does. PEFT reads ``adapter_config.json``; that file
in ``recsi.zip`` contains a non-portable Windows ``base_model_name_or_path``,
which PEFT tolerates because we pass the already-loaded ``model`` object.
See ``configuration/README.md`` if you want to normalise that field.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from .settings import InferenceSettings, get_settings

logger = logging.getLogger("recipe_inference.model_loader")

_lock = threading.Lock()
_state: dict[str, Any] = {"tokenizer": None, "model": None, "loaded": False}
_load_error: Optional[str] = None


def _torch_dtype(torch, name: str):
    mapping = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return mapping.get(name, torch.bfloat16)


def _cuda_available(torch) -> bool:
    try:
        return bool(torch.cuda.is_available())
    except Exception:  # pragma: no cover - defensive
        return False


def load(settings: Optional[InferenceSettings] = None):
    """Load tokenizer + (base + adapter) model once, returning ``(tok, model)``.

    Raises ``RuntimeError`` with an actionable message on any failure so the
    service can report a clear readiness error instead of a stack trace.
    """
    global _load_error
    settings = settings or get_settings()

    with _lock:
        if _state["loaded"]:
            return _state["tokenizer"], _state["model"]
        try:
            tokenizer, model = _build(settings)
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            _load_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Model load failed")
            raise RuntimeError(_load_error) from exc

        _state.update(tokenizer=tokenizer, model=model, loaded=True)
        _load_error = None
        return tokenizer, model


def _build(settings: InferenceSettings):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    using_local = bool(settings.base_model_local)
    source = settings.base_model_local or settings.base_model_id

    tokenizer = AutoTokenizer.from_pretrained(
        source,
        revision=None if using_local else settings.base_revision,
        local_files_only=using_local,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_config = None
    want_4bit = settings.load_in_4bit and _cuda_available(torch)
    if settings.load_in_4bit and not _cuda_available(torch):
        logger.warning(
            "CUDA not available: falling back to unquantized CPU/CPU-offload load. "
            "4-bit NF4 requires a CUDA GPU (see HARDWARE_REQUIREMENTS.md)."
        )

    if want_4bit:
        from transformers import BitsAndBytesConfig

        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=settings.bnb_quant_type,
            bnb_4bit_use_double_quant=settings.bnb_double_quant,
            bnb_4bit_compute_dtype=_torch_dtype(torch, settings.compute_dtype),
        )

    model_kwargs: dict[str, Any] = {
        "local_files_only": using_local,
        "dtype": _torch_dtype(torch, settings.compute_dtype),
    }
    if not using_local:
        model_kwargs["revision"] = settings.base_revision
    if quant_config is not None:
        model_kwargs["quantization_config"] = quant_config
        model_kwargs["device_map"] = settings.device_map
    elif _cuda_available(torch):
        model_kwargs["device_map"] = settings.device_map

    model = AutoModelForCausalLM.from_pretrained(source, **model_kwargs)

    adapter_dir = settings.adapter_dir()
    if adapter_dir is not None:
        if not (adapter_dir / "adapter_config.json").is_file():
            raise RuntimeError(
                f"Adapter directory has no adapter_config.json: {adapter_dir}"
            )
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter_dir))
        logger.info("Attached LoRA adapter from %s", adapter_dir)
    else:
        logger.warning(
            "No LoRA adapter configured (RECIPE_ADAPTER_PATH unset and no "
            "'model/' or 'recsi/model/' directory found). Serving BASE model."
        )

    model.eval()
    return tokenizer, model


def is_ready() -> bool:
    return bool(_state["loaded"])


def readiness() -> dict:
    """Report readiness without triggering a load."""
    return {
        "model_loaded": bool(_state["loaded"]),
        "last_error": _load_error,
    }


def unload() -> None:
    """Drop references (used by tests)."""
    global _load_error
    with _lock:
        _state.update(tokenizer=None, model=None, loaded=False)
        _load_error = None
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover
        pass
