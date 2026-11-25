import os
from pathlib import Path

import torch

from training.freshness_model import FreshnessModel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT = PROJECT_ROOT / "outputs" / "freshness_v1" / "best_model.pt"


class FreshnessInferenceEngine:
    def __init__(self):
        self.device = self._select_device()
        self.checkpoint_path = Path(
            os.getenv("FRESHNESS_CHECKPOINT", str(DEFAULT_CHECKPOINT))
        ).resolve()

        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(
                f"Freshness checkpoint not found: {self.checkpoint_path}"
            )

        checkpoint = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=False,
        )

        required = {
            "model_state_dict",
            "category_names",
            "category_to_idx",
            "label_to_idx",
            "config",
        }
        missing = required - set(checkpoint)

        if missing:
            raise ValueError(
                f"Checkpoint is missing keys: {sorted(missing)}"
            )

        self.category_names = list(checkpoint["category_names"])
        self.category_to_idx = dict(checkpoint["category_to_idx"])
        self.label_to_idx = {
            category: dict(mapping)
            for category, mapping in checkpoint["label_to_idx"].items()
        }

        if len(self.category_names) != 24:
            raise ValueError("Expected exactly 24 freshness categories")

        expected_indices = {
            name: index
            for index, name in enumerate(self.category_names)
        }
        if self.category_to_idx != expected_indices:
            raise ValueError("Checkpoint category indices are inconsistent")

        if set(self.label_to_idx) != set(self.category_names):
            raise ValueError("Checkpoint label mappings are inconsistent")

        dropout = float(checkpoint["config"].get("dropout", 0.30))

        self.model = FreshnessModel(
            category_names=self.category_names,
            label_to_idx=self.label_to_idx,
            pretrained=False,
            dropout=dropout,
        )

        self.model.load_state_dict(
            checkpoint["model_state_dict"],
            strict=True,
        )
        self.model.to(self.device)
        self.model.eval()

        self.epoch = int(checkpoint["epoch"])
        self.validation_macro_f1 = float(
            checkpoint["best_validation_macro_f1"]
        )

        del checkpoint

    @staticmethod
    def _select_device():
        requested = os.getenv("FRESHNESS_DEVICE", "auto").lower()

        if requested == "auto":
            return torch.device(
                "cuda" if torch.cuda.is_available() else "cpu"
            )

        if requested == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "FRESHNESS_DEVICE=cuda but CUDA is unavailable"
                )
            return torch.device("cuda")

        if requested == "cpu":
            return torch.device("cpu")

        raise ValueError(
            "FRESHNESS_DEVICE must be auto, cpu, or cuda"
        )

    def predict(self, image_tensor, category):
        category = category.strip().lower()

        if category not in self.category_to_idx:
            raise ValueError(f"Unsupported freshness category: {category}")

        category_idx = self.category_to_idx[category]

        image_tensor = image_tensor.unsqueeze(0).to(self.device)
        category_tensor = torch.tensor(
            [category_idx],
            dtype=torch.long,
            device=self.device,
        )

        with torch.inference_mode():
            outputs = self.model(image_tensor, category_tensor)
            _, logits = outputs[category_idx]
            probabilities = torch.softmax(logits[0], dim=0)

        index_to_label = {
            index: label
            for label, index in self.label_to_idx[category].items()
        }

        scores = {
            index_to_label[index]: float(probabilities[index].item())
            for index in range(len(index_to_label))
        }

        predicted_label = max(scores, key=scores.get)

        return {
            "category": category,
            "predicted_label": predicted_label,
            "confidence": scores[predicted_label],
            "probabilities": scores,
        }
