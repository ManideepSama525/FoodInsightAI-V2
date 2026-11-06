#!/usr/bin/env python3
"""Standalone FoodInsightAI Food-101 inference using the exported TorchScript model."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps


def load_artifacts(artifact_dir: Path, requested_device: str):
    model_path = artifact_dir / "food_classifier.ts"
    classes_path = artifact_dir / "classes.json"
    metrics_path = artifact_dir / "training_metrics.json"

    missing = [str(p) for p in (model_path, classes_path) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Required artifact(s) missing:\n  " + "\n  ".join(missing)
        )

    classes = json.loads(classes_path.read_text(encoding="utf-8"))
    if not isinstance(classes, list) or not classes:
        raise ValueError("classes.json must contain a non-empty JSON list.")

    if requested_device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(requested_device)

    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot access CUDA.")

    # The training script exports food_classifier.ts on CPU.
    model = torch.jit.load(str(model_path), map_location=device)
    model.eval()

    metadata = None
    if metrics_path.is_file():
        metadata = json.loads(metrics_path.read_text(encoding="utf-8"))

    return model, classes, device, metadata


def preprocess_image(image_path: Path, device: torch.device):
    # Match InferenceCompatibleFit in train_food101.py:
    # EXIF transpose -> RGB -> ImageOps.fit(224x224, bilinear).
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image = ImageOps.fit(
            image,
            (224, 224),
            method=Image.Resampling.BILINEAR,
        )
        array = np.asarray(image, dtype=np.float32) / 255.0

    tensor = torch.from_numpy(array).permute(2, 0, 1).contiguous()

    mean = torch.tensor((0.485, 0.456, 0.406), dtype=torch.float32).view(3, 1, 1)
    std = torch.tensor((0.229, 0.224, 0.225), dtype=torch.float32).view(3, 1, 1)
    tensor = (tensor - mean) / std

    return tensor.unsqueeze(0).to(device)


@torch.inference_mode()
def predict(model, image_tensor, classes, top_k):
    logits = model(image_tensor)

    if isinstance(logits, (tuple, list)):
        logits = logits[0]
    if not isinstance(logits, torch.Tensor):
        raise TypeError(f"Model returned unsupported output type: {type(logits)}")
    if logits.ndim != 2 or logits.shape[0] != 1:
        raise ValueError(f"Expected model output shape [1, num_classes], got {tuple(logits.shape)}")
    if logits.shape[1] != len(classes):
        raise ValueError(
            f"Model has {logits.shape[1]} outputs but classes.json has {len(classes)} classes."
        )
    if not torch.isfinite(logits).all():
        raise ValueError("Model produced NaN or infinite logits.")

    probabilities = torch.softmax(logits.float(), dim=1)[0]
    values, indices = torch.topk(probabilities, k=min(top_k, len(classes)))

    return [
        (classes[int(index)], float(value) * 100.0)
        for value, index in zip(values.cpu(), indices.cpu())
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Run FoodInsightAI Food-101 image classification."
    )
    parser.add_argument("--image", type=Path, help="Path to a food image.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory containing food_classifier.ts and classes.json (default: artifacts).",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Inference device (default: auto).",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of predictions to show.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Load artifacts and verify model output dimensions without an image.",
    )
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1.")
    if not args.verify_only and args.image is None:
        parser.error("Provide --image PATH or use --verify-only.")
    if args.image is not None and not args.image.is_file():
        parser.error(f"Image not found: {args.image}")

    model, classes, device, metadata = load_artifacts(
        args.artifacts_dir, args.device
    )

    print(f"Model: {args.artifacts_dir / 'food_classifier.ts'}")
    print(f"Classes: {len(classes)}")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(device)}")

    if metadata:
        print(f"Architecture: {metadata.get('architecture', 'not recorded')}")
        print(f"Best checkpoint epoch: {metadata.get('best_checkpoint_epoch', 'not recorded')}")
        test_metrics = metadata.get("test", {})
        if test_metrics:
            print(
                "Recorded official test Top-1: "
                f"{test_metrics.get('top1_accuracy', 'not recorded')}"
            )

    if args.verify_only:
        dummy = torch.zeros(1, 3, 224, 224, device=device)
        with torch.inference_mode():
            output = model(dummy)
        if isinstance(output, (tuple, list)):
            output = output[0]
        if not isinstance(output, torch.Tensor) or output.shape != (1, len(classes)):
            raise RuntimeError(
                f"Artifact verification failed: expected output [1, {len(classes)}], "
                f"got {getattr(output, 'shape', type(output))}"
            )
        if not torch.isfinite(output).all():
            raise RuntimeError("Artifact verification failed: model output is non-finite.")
        print("Artifact verification: PASS")
        print(f"Output shape: {tuple(output.shape)}")
        return

    image_tensor = preprocess_image(args.image, device)
    predictions = predict(model, image_tensor, classes, args.top_k)

    print(f"\nImage: {args.image}")
    print(f"Top-{len(predictions)} predictions:")
    for rank, (class_name, confidence) in enumerate(predictions, start=1):
        print(f"{rank}. {class_name}: {confidence:.2f}%")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
