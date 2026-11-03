from dataclasses import dataclass
from pathlib import Path
import json
from typing import Protocol

from PIL import Image

@dataclass(frozen=True)
class RawPrediction:
    class_index: int
    confidence: float

@dataclass(frozen=True)
class RecognitionResult:
    predicted_food: str | None
    confidence: float | None
    needs_review: bool
    model_version: str
    top_predictions: list[tuple[str, float]]
    message: str | None = None

class ModelNotReadyError(RuntimeError):
    pass

class InferenceRuntime(Protocol):
    def predict(self, image: Image.Image, top_k: int) -> list[RawPrediction]: ...

class PredictionProvider(Protocol):
    def predict(self, content: bytes, top_k: int = 5) -> RecognitionResult: ...

class UnavailablePredictionProvider:
    def predict(self, content: bytes, top_k: int = 5) -> RecognitionResult:
        raise ModelNotReadyError(
            "Food recognition model is not configured. Add a trained TorchScript model and class-label file."
        )

class RecognitionService:
    def __init__(
        self,
        runtime: InferenceRuntime,
        class_labels: list[str],
        model_version: str,
        confidence_threshold: float = 0.65,
        image_size: int = 224,
    ) -> None:
        if not class_labels or any(not label.strip() for label in class_labels):
            raise ValueError("class_labels must contain non-empty labels")
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.runtime = runtime
        self.class_labels = class_labels
        self.model_version = model_version
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size

    def predict(self, content: bytes, top_k: int = 5) -> RecognitionResult:
        from backend.app.services.recognition.preprocessing import prepare_image

        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        prepared = prepare_image(content, self.image_size)
        raw = self.runtime.predict(prepared.image, min(top_k, len(self.class_labels)))
        valid = [
            item for item in raw
            if 0 <= item.class_index < len(self.class_labels)
            and 0.0 <= item.confidence <= 1.0
        ]
        valid.sort(key=lambda item: item.confidence, reverse=True)
        if not valid:
            return RecognitionResult(None, None, True, self.model_version, [], "Model returned no valid predictions.")
        best = valid[0]
        label = self.class_labels[best.class_index]
        needs_review = best.confidence < self.confidence_threshold
        return RecognitionResult(
            predicted_food=None if needs_review else label,
            confidence=best.confidence,
            needs_review=needs_review,
            model_version=self.model_version,
            top_predictions=[(self.class_labels[p.class_index], p.confidence) for p in valid[:top_k]],
            message="Low confidence: user confirmation is required." if needs_review else None,
        )

class TorchScriptRuntime:
    """Optional CPU-capable TorchScript adapter. Import torch only when this runtime is selected."""
    def __init__(self, model_path: Path) -> None:
        try:
            import torch
        except ImportError as exc:
            raise ModelNotReadyError("Install the optional 'vision' dependencies to run inference.") from exc
        if not model_path.is_file():
            raise ModelNotReadyError(f"Model artifact not found: {model_path}")
        self._torch = torch
        self._model = torch.jit.load(str(model_path), map_location="cpu")
        self._model.eval()

    def predict(self, image: Image.Image, top_k: int) -> list[RawPrediction]:
        import numpy as np
        array = np.asarray(image, dtype="float32") / 255.0
        tensor = self._torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0)
        mean = self._torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        std = self._torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
        with self._torch.inference_mode():
            logits = self._model((tensor - mean) / std)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            probabilities = self._torch.softmax(logits, dim=1)[0]
            scores, indices = self._torch.topk(probabilities, k=min(top_k, probabilities.numel()))
        return [
            RawPrediction(int(index.item()), float(score.item()))
            for score, index in zip(scores, indices, strict=True)
        ]

def build_prediction_provider(
    model_path: Path,
    labels_path: Path,
    model_version: str,
    confidence_threshold: float,
    image_size: int,
) -> PredictionProvider:
    if not model_path.is_file() or not labels_path.is_file():
        return UnavailablePredictionProvider()
    try:
        labels_data = json.loads(labels_path.read_text(encoding="utf-8"))
        labels = labels_data["classes"] if isinstance(labels_data, dict) else labels_data
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise ValueError("Label file must be a JSON list or an object with a 'classes' list.")
        runtime = TorchScriptRuntime(model_path)
        return RecognitionService(runtime, labels, model_version, confidence_threshold, image_size)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ModelNotReadyError(f"Could not load recognition model configuration: {exc}") from exc
