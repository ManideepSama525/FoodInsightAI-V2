#!/usr/bin/env python3
"""Evaluate a TorchScript Food-101 classifier on the official test split."""
import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset


def load_classes(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        classes = data
    elif isinstance(data, dict):
        if isinstance(data.get("classes"), list):
            classes = data["classes"]
        elif all(isinstance(v, int) for v in data.values()):
            classes = [name for name, _ in sorted(data.items(), key=lambda item: item[1])]
        elif all(str(k).isdigit() for k in data.keys()):
            classes = [name for _, name in sorted(data.items(), key=lambda item: int(item[0]))]
        else:
            raise ValueError("Unsupported classes.json format.")
    else:
        raise ValueError("classes.json must contain a list or a supported dictionary.")

    if not all(isinstance(name, str) for name in classes):
        raise ValueError("Class names must all be strings.")
    return classes


class OfficialFood101Test(Dataset):
    def __init__(self, root: Path, entries, class_to_idx):
        self.root = root
        self.entries = entries
        self.class_to_idx = class_to_idx

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, index):
        relative_path, class_name = self.entries[index]
        image_path = self.root / "images" / (relative_path + ".jpg")
        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image = ImageOps.fit(
                    image, (224, 224), method=Image.Resampling.BILINEAR
                )
                array = np.asarray(image, dtype=np.float32) / 255.0

            tensor = torch.from_numpy(array).permute(2, 0, 1)
            mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32)[:, None, None]
            std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32)[:, None, None]
            tensor = (tensor - mean) / std
            return tensor, self.class_to_idx[class_name], relative_path, ""
        except Exception as exc:
            return None, self.class_to_idx[class_name], relative_path, str(exc)


def collate_valid(batch):
    valid = [item for item in batch if item[0] is not None]
    errors = [(item[2], item[3]) for item in batch if item[0] is None]
    if not valid:
        return None, None, [], errors
    images = torch.stack([item[0] for item in valid])
    labels = torch.tensor([item[1] for item in valid], dtype=torch.long)
    paths = [item[2] for item in valid]
    return images, labels, paths, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", default="/workspace/artifacts")
    parser.add_argument("--dataset-root", default="/workspace/food101")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()

    artifacts = Path(args.artifacts_dir)
    dataset_root = Path(args.dataset_root)
    model_path = artifacts / "food_classifier.ts"
    classes_path = artifacts / "classes.json"
    split_path = dataset_root / "meta" / "test.txt"

    for required in (model_path, classes_path, split_path):
        if not required.is_file():
            raise FileNotFoundError(f"Required file not found: {required}")

    classes = load_classes(classes_path)
    class_to_idx = {name: i for i, name in enumerate(classes)}
    if len(classes) != 101:
        raise ValueError(f"Expected 101 classes, found {len(classes)}")

    entries = []
    with split_path.open("r", encoding="utf-8") as f:
        for line in f:
            relative_path = line.strip()
            if not relative_path:
                continue
            class_name = relative_path.split("/", 1)[0]
            if class_name not in class_to_idx:
                raise ValueError(f"Class '{class_name}' from test.txt is absent from classes.json")
            entries.append((relative_path, class_name))

    if len(entries) != 25250:
        raise ValueError(f"Expected 25,250 official test entries, found {len(entries)}")

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")
    device = torch.device(
        "cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )

    print(f"Model: {model_path}", flush=True)
    print(f"Dataset root: {dataset_root}", flush=True)
    print(f"Official test images: {len(entries)}", flush=True)
    print(f"Classes: {len(classes)}", flush=True)
    print(f"Device: {device}", flush=True)
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)

    model = torch.jit.load(str(model_path), map_location=device)
    model.eval()

    dataset = OfficialFood101Test(dataset_root, entries, class_to_idx)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
        collate_fn=collate_valid,
    )

    n_classes = len(classes)
    confusion = np.zeros((n_classes, n_classes), dtype=np.int64)
    class_total = np.zeros(n_classes, dtype=np.int64)
    class_correct = np.zeros(n_classes, dtype=np.int64)
    top1_correct = 0
    top5_correct = 0
    processed = 0
    errors = []
    prediction_rows = []
    start = time.perf_counter()

    with torch.inference_mode():
        for batch_number, (images, labels, paths, batch_errors) in enumerate(loader, start=1):
            errors.extend(batch_errors)
            if images is None:
                continue

            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            logits = model(images)
            top5 = torch.topk(logits, k=5, dim=1)
            predictions = top5.indices[:, 0]
            matches = predictions.eq(labels)

            top1_correct += int(matches.sum().item())
            top5_correct += int(top5.indices.eq(labels[:, None]).any(dim=1).sum().item())
            processed += labels.size(0)

            labels_cpu = labels.cpu().numpy()
            predictions_cpu = predictions.cpu().numpy()
            scores_cpu = torch.softmax(logits, dim=1).cpu().numpy()
            top5_indices = top5.indices.cpu().numpy()

            for i, (true_idx, pred_idx, relative_path) in enumerate(
                zip(labels_cpu, predictions_cpu, paths)
            ):
                confusion[true_idx, pred_idx] += 1
                class_total[true_idx] += 1
                if true_idx == pred_idx:
                    class_correct[true_idx] += 1
                top5_text = " | ".join(
                    f"{classes[int(idx)]}:{scores_cpu[i, int(idx)] * 100:.4f}%"
                    for idx in top5_indices[i]
                )
                prediction_rows.append([
                    relative_path,
                    classes[int(true_idx)],
                    classes[int(pred_idx)],
                    f"{scores_cpu[i, int(pred_idx)] * 100:.4f}",
                    top5_text,
                    int(true_idx == pred_idx),
                ])

            if batch_number % 100 == 0 or processed + len(errors) >= len(entries):
                print(
                    f"Processed {processed + len(errors)}/{len(entries)} "
                    f"(valid predictions: {processed}, skipped: {len(errors)})",
                    flush=True,
                )

    elapsed = time.perf_counter() - start
    if processed == 0:
        raise RuntimeError("No test images were successfully processed.")

    top1 = top1_correct / processed
    top5_accuracy = top5_correct / processed
    per_class_rows = []
    for idx, name in enumerate(classes):
        accuracy = (class_correct[idx] / class_total[idx]) if class_total[idx] else 0.0
        per_class_rows.append([name, int(class_total[idx]), int(class_correct[idx]), f"{accuracy:.6f}"])

    artifacts.mkdir(parents=True, exist_ok=True)
    predictions_path = artifacts / "official_test_predictions.csv"
    per_class_path = artifacts / "per_class_accuracy.csv"
    confusion_path = artifacts / "official_test_confusion_matrix.csv"
    errors_path = artifacts / "official_test_errors.csv"
    metrics_path = artifacts / "official_test_metrics.json"

    with predictions_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "actual_class", "predicted_class", "confidence_percent", "top5_predictions", "correct"])
        writer.writerows(prediction_rows)

    with per_class_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["class", "test_images", "correct_predictions", "top1_accuracy"])
        writer.writerows(per_class_rows)

    with confusion_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["actual\\predicted"] + classes)
        for idx, name in enumerate(classes):
            writer.writerow([name] + confusion[idx].tolist())

    with errors_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "error"])
        writer.writerows(errors)

    metrics = {
        "dataset": "Food-101 official test split",
        "expected_images": len(entries),
        "processed_images": processed,
        "skipped_images": len(errors),
        "top1_accuracy": top1,
        "top5_accuracy": top5_accuracy,
        "top1_correct": top1_correct,
        "top5_correct": top5_correct,
        "elapsed_seconds": elapsed,
        "average_ms_per_processed_image": elapsed * 1000 / processed,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "class_count": n_classes,
    }
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("\n===== OFFICIAL FOOD-101 TEST RESULTS =====")
    print(f"Expected images:       {len(entries)}")
    print(f"Processed images:      {processed}")
    print(f"Skipped images:        {len(errors)}")
    print(f"Top-1 accuracy:        {top1:.4%} ({top1_correct}/{processed})")
    print(f"Top-5 accuracy:        {top5_accuracy:.4%} ({top5_correct}/{processed})")
    print(f"Elapsed time:          {elapsed:.2f} seconds")
    print(f"Average time/image:    {elapsed * 1000 / processed:.2f} ms")
    print("\nReports saved:")
    print(f"  Metrics:             {metrics_path}")
    print(f"  Predictions:         {predictions_path}")
    print(f"  Per-class accuracy:  {per_class_path}")
    print(f"  Confusion matrix:    {confusion_path}")
    print(f"  Skipped images:      {errors_path}")


if __name__ == "__main__":
    main()
