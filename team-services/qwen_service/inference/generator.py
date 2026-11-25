"""Recipe generation entry point (inference).

``generate_recipe`` is the single function the inference API exposes. It is a
thin, faithful wrapper around the generation loop used by the original
project's evaluation harness (``training/evaluate.py``):

    tokenizer.apply_chat_template(messages, tokenize=False,
                                  add_generation_prompt=True,
                                  enable_thinking=False)
    model.generate(max_new_tokens=..., do_sample=False,
                   repetition_penalty=1.05,
                   pad_token_id=tokenizer.eos_token_id)

Greedy decoding (``do_sample=False``) is used deliberately: it matches the
evaluation run whose numbers are shipped in ``evaluation/``, so results are
comparable. The base model's ``generation_config.json`` (temperature 0.6,
top_p 0.95) is therefore *overridden*.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from . import model_loader, prompts
from .parsing import recipe_format, split_sections, strip_role_prefixes
from .settings import InferenceSettings, get_settings

logger = logging.getLogger("recipe_inference.generator")


class GenerationTimeout(RuntimeError):
    """Raised when generation exceeds the configured wall-clock budget."""


def _build_inputs(tokenizer, messages, enable_thinking: bool):
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    return tokenizer(prompt, return_tensors="pt")


def generate_recipe(
    title: str,
    *,
    max_new_tokens: Optional[int] = None,
    timeout_s: float = 60.0,
    settings: Optional[InferenceSettings] = None,
) -> dict:
    """Generate a recipe for ``title``.

    Returns a dict:
      ``{"title", "raw", "answer", "ingredients", "steps", "format", "seconds"}``
    """
    settings = settings or get_settings()
    title = (title or "").strip()
    if not title:
        raise ValueError("title must be a non-empty string")

    import torch

    tokenizer, model = model_loader.load(settings)
    messages = prompts.recipe_messages(title)
    inputs = _build_inputs(tokenizer, messages, settings.enable_thinking).to(model.device)

    max_new_tokens = int(max_new_tokens or settings.max_new_tokens)
    generate_kwargs = {
        "max_new_tokens": max_new_tokens,
        "do_sample": settings.do_sample,
        "repetition_penalty": settings.repetition_penalty,
        "pad_token_id": tokenizer.eos_token_id,
    }
    # transformers supports a soft wall-clock cap via ``max_time``; pass it when
    # the installed version understands it (harmless kwarg otherwise).
    if timeout_s and timeout_s > 0:
        generate_kwargs["max_time"] = float(timeout_s)
    if settings.do_sample:
        generate_kwargs.update(temperature=0.6, top_p=0.95, top_k=20)

    t0 = time.time()
    with torch.inference_mode():
        output = model.generate(**inputs, **generate_kwargs)
    seconds = round(time.time() - t0, 2)

    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    raw = tokenizer.decode(new_tokens, skip_special_tokens=True)
    answer = strip_role_prefixes(raw)

    sections = split_sections(answer)
    return {
        "title": title,
        "raw": raw,
        "answer": answer,
        "ingredients": sections["ingredients"],
        "steps": sections["steps"],
        "format": recipe_format(answer),
        "seconds": seconds,
    }


def generate_chat(
    messages: list[dict],
    *,
    max_new_tokens: Optional[int] = None,
    timeout_s: float = 60.0,
    settings: Optional[InferenceSettings] = None,
) -> dict:
    """Low-level generation for arbitrary chat messages (used by tests)."""
    settings = settings or get_settings()
    import torch

    tokenizer, model = model_loader.load(settings)
    inputs = _build_inputs(tokenizer, messages, settings.enable_thinking).to(model.device)
    generate_kwargs = {
        "max_new_tokens": int(max_new_tokens or settings.max_new_tokens),
        "do_sample": settings.do_sample,
        "repetition_penalty": settings.repetition_penalty,
        "pad_token_id": tokenizer.eos_token_id,
    }
    if timeout_s and timeout_s > 0:
        generate_kwargs["max_time"] = float(timeout_s)

    with torch.inference_mode():
        output = model.generate(**inputs, **generate_kwargs)
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    return {"answer": strip_role_prefixes(tokenizer.decode(new_tokens, skip_special_tokens=True))}
