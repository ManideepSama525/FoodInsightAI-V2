#!/usr/bin/env python3
"""Batch inference for FoodInsightAI's exported Food-101 TorchScript model."""

import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def load_model(artifact_dir: Path, device_name: str):
    model_path = artifact_dir / "food_classifier.ts"
    classes_path = artifact_dir / "classes.json"

    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not classes_path.is_file():
        raise FileNotFoundError(f"Class list not found: {classes_path}")

    classes = json.loads(classes_path.read_text(encoding="utf-8"))
    if not isinstance(classes, list) or len(classes) != 101:
        raise ValueError(f"Expected 101 class names; found {len(classes) if isinstance(classes, list) else 'invalid data'}.")

    if device_name == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device_name)

    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable.")

    model = torch.jit.load(str(model_path), map_location=device).eval()
    return model, classes, device


def preprocess(path: Path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image = ImageOps.fit(
            image, (224, 224), method=Image.Resampling.BILINEAR
        )
        array = np.asarray(image, dtype=np.float32) / 255.0

    tensor = torch.from_numpy(array).permute(2, 0, 1).contiguous()
    mean = torch.tensor((0.485, 0.456, 0.406)).view(3, 1, 1)
    std = torch.tensor((0.229, 0.224, 0.225)).view(3, 1, 1)
    return (tensor - mean) / std


def collect_images(input_path: Path):
    if input_path.is_file():
        if input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {input_path.suffix}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    return sorted(
        p for p in input_path.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run FoodInsightAI predictions on a folder of food images."
    )
    parser.add_argument("--input", type=Path, required=True,
                        help="Image file or folder containing images.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/batch_predictions.csv"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    model, classes, device = load_model(args.artifacts_dir, args.device)
    images = collect_images(args.input)
    if not images:
        raise RuntimeError(f"No supported images found in {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Model: {args.artifacts_dir / 'food_classifier.ts'}")
    print(f"Classes: {len(classes)}")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(device)}")
    print(f"Images found: {len(images)}")
    print(f"Batch size: {args.batch_size}")

    rows = []
    errors = []
    correct = 0
    labeled = 0
    total_inference_seconds = 0.0
    class_to_index = {name: i for i, name in enumerate(classes)}

    for start in range(0, len(images), args.batch_size):
        batch_paths = images[start:start + args.batch_size]
        tensors = []
        valid_paths = []

        for image_path in batch_paths:
            try:
                tensors.append(preprocess(image_path))
                valid_paths.append(image_path)
            except Exception as exc:
                errors.append((str(image_path), str(exc)))
                print(f"SKIP: {image_path} ({exc})")

        if not tensors:
            continue

        batch = torch.stack(tensors).to(device)
        if device.type == "cuda":
            torch.cuda.synchronize()
        inference_start = time.perf_counter()

        with torch.inference_mode():
            logits = model(batch)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            if not isinstance(logits, torch.Tensor):
                raise TypeError(f"Unexpected model output: {type(logits)}")
            if logits.ndim != 2 or logits.shape != (len(valid_paths), len(classes)):
                raise ValueError(f"Unexpected output shape: {tuple(logits.shape)}")
            if not torch.isfinite(logits).all():
                raise ValueError("Model produced NaN or infinite logits.")
            probabilities = torch.softmax(logits.float(), dim=1)
            values, indices = torch.topk(
                probabilities, k=min(args.top_k, len(classes)), dim=1
            )

        if device.type == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - inference_start
        total_inference_seconds += elapsed
        per_image_ms = elapsed * 1000.0 / len(valid_paths)

        for row_index, image_path in enumerate(valid_paths):
            top_items = [
                (classes[int(indices[row_index, rank])],
                 float(values[row_index, rank]) * 100.0)
                for rank in range(values.shape[1])
            ]
            predicted_class, confidence = top_items[0]

            # If images are stored in class-named subfolders, use the parent
            # folder as a label only when it exactly matches a Food-101 class.
            actual_class = image_path.parent.name
            is_labeled = actual_class in class_to_index
            is_correct = is_labeled and predicted_class == actual_class
            if is_labeled:
                labeled += 1
                correct += int(is_correct)

            rows.append({
                "image": str(image_path),
                "predicted_class": predicted_class,
                "confidence_percent": f"{confidence:.4f}",
                "top_k_predictions": " | ".join(
                    f"{name}:{score:.4f}%" for name, score in top_items
                ),
                "actual_class_from_folder": actual_class if is_labeled else "",
                "correct": str(is_correct).lower() if is_labeled else "",
                "inference_ms_per_image_batch_average": f"{per_image_ms:.3f}",
            })

        print(f"Processed {min(start + args.batch_size, len(images))}/{len(images)}")

    fieldnames = [
        "image", "predicted_class", "confidence_percent",
        "top_k_predictions", "actual_class_from_folder", "correct",
        "inference_ms_per_image_batch_average",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n===== BATCH INFERENCE SUMMARY =====")
    print(f"Images discovered: {len(images)}")
    print(f"Images predicted: {len(rows)}")
    print(f"Images skipped: {len(errors)}")
    if rows:
        print(f"Average batch inference time per image: "
              f"{total_inference_seconds * 1000.0 / len(rows):.3f} ms")
    if labeled:
        print(f"Folder-labeled images: {labeled}")
        print(f"Top-1 folder-label accuracy: {correct / labeled * 100:.2f}%")
    else:
        print("Accuracy: not calculated (images were not in class-named folders).")
    print(f"CSV report: {args.output}")

    if errors:
        error_path = args.output.with_name(args.output.stem + "_errors.csv")
        with error_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["image", "error"])
            writer.writerows(errors)
        print(f"Error report: {error_path}")


if __name__ == "__main__":
    main()
