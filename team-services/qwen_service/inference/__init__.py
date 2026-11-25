"""Standalone recipe-generation inference package.

This package hosts the *newly authored* LoRA inference path for the
FoodInsightAI recipe generator. It is intentionally independent from the
recipient project's FastAPI backend so that it can run in its own
dependency environment (see ``deployment/``).

Nothing in this package is executed at import time; the heavy ML libraries
(``torch``, ``transformers``, ``peft``, ``bitsandbytes``) are imported lazily
inside ``model_loader.load()`` so that ``prompts``/``parsing`` helpers remain
usable without a GPU stack installed.
"""

__all__ = [
    "settings",
    "prompts",
    "parsing",
    "model_loader",
    "generator",
    "schemas",
    "service",
]

__version__ = "0.1.0"
