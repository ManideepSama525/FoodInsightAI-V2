from __future__ import annotations

import threading
from typing import Sequence

from backend.app.core.config import get_settings


QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingService:
    """Lazy, CPU-only BGE embedding service.

    Model loading is explicit and does not happen during API startup.
    """

    def __init__(self) -> None:
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return get_settings().embedding_model_name

    @property
    def dimensions(self) -> int:
        return get_settings().embedding_dimensions

    def _load(self) -> None:
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            import torch
            from transformers import AutoModel, AutoTokenizer

            settings = get_settings()
            cache_dir = str(settings.embedding_cache_dir)
            tokenizer = AutoTokenizer.from_pretrained(
                settings.embedding_model_name,
                cache_dir=cache_dir,
            )
            model = AutoModel.from_pretrained(
                settings.embedding_model_name,
                cache_dir=cache_dir,
            )
            model.to("cpu")
            model.eval()

            hidden_size = int(model.config.hidden_size)
            if hidden_size != settings.embedding_dimensions:
                raise RuntimeError(
                    f"Embedding model returned {hidden_size} dimensions; "
                    f"expected {settings.embedding_dimensions}"
                )

            self._torch = torch
            self._tokenizer = tokenizer
            self._model = model

    def encode(
        self,
        texts: Sequence[str],
        *,
        query: bool = False,
        batch_size: int | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(item, str) or not item.strip() for item in texts):
            raise ValueError("Embedding inputs must be non-empty strings")

        self._load()
        settings = get_settings()
        size = batch_size or settings.embedding_batch_size
        if not 1 <= size <= 128:
            raise ValueError("batch_size must be between 1 and 128")

        prepared = [
            (QUERY_PREFIX + item.strip()) if query else item.strip()
            for item in texts
        ]
        results: list[list[float]] = []

        for offset in range(0, len(prepared), size):
            batch = prepared[offset:offset + size]
            tokens = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            with self._torch.inference_mode():
                output = self._model(**tokens)
                token_embeddings = output.last_hidden_state
                mask = tokens["attention_mask"].unsqueeze(-1).to(
                    token_embeddings.dtype
                )
                summed = (token_embeddings * mask).sum(dim=1)
                counts = mask.sum(dim=1).clamp(min=1)
                pooled = summed / counts
                normalized = self._torch.nn.functional.normalize(
                    pooled, p=2, dim=1
                )

            vectors = normalized.cpu().tolist()
            if any(len(vector) != self.dimensions for vector in vectors):
                raise RuntimeError("Embedding output has an unexpected dimension")
            results.extend([[float(value) for value in vector] for vector in vectors])

        return results


embedding_service = EmbeddingService()
