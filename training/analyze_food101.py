import argparse
import csv
import html
import json
import time
from collections import defaultdict
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader
from PIL import Image, ImageOps


class Food101TestDataset(Dataset):
    def __init__(self, root, classes):
        self.root = Path(root)
        self.classes = classes
        self.class_to_idx = {name: i for i, name in enumerate(classes)}
        meta = self.root / "meta" / "test.txt"
        self.samples = []

        for line in meta.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            label, image_id = line.strip().split("/")
            if label not in self.class_to_idx:
                raise ValueError(f"Unknown class in test split: {label}")
            image_path = self.root / "images" / label / f"{image_id}.jpg"
            self.samples.append((image_path, self.class_to_idx[label], label))

        if not self.samples:
            raise RuntimeError("Official test split is empty")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        path, label, name = self.samples[index]
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(
                image, (224, 224), method=Image.Resampling.BILINEAR
            )
            import numpy as np
            array = np.asarray(image, dtype=np.float32) / 255.0

        tensor = torch.from_numpy(array).permute(2, 0, 1)
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        tensor = (tensor - mean) / std
        return tensor, label, str(path), name


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/workspace/data/food101/food-101")
    parser.add_argument("--artifacts", default="/workspace/artifacts")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--high-confidence", type=float, default=0.80)
    args = parser.parse_args()

    data_root = Path(args.data)
    artifact_root = Path(args.artifacts)
    output = artifact_root / "error_analysis"
    output.mkdir(parents=True, exist_ok=True)

    classes = json.loads((artifact_root / "classes.json").read_text())
    model_path = artifact_root / "food_classifier.ts"

    if not model_path.exists():
        raise FileNotFoundError(model_path)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    dataset = Food101TestDataset(data_root, classes)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=(device.type == "cuda"),
    )

    model = torch.jit.load(str(model_path), map_location=device)
    model.eval()

    class_count = len(classes)
    correct1 = 0
    correct5 = 0
    processed = 0
    class_total = [0] * class_count
    class_correct = [0] * class_count
    class_top5 = [0] * class_count
    confusion = [[0] * class_count for _ in range(class_count)]
    prediction_rows = []
    error_rows = []
    pair_counts = defaultdict(int)
    started = time.time()

    with torch.inference_mode():
        for batch_index, (images, labels, paths, actual_names) in enumerate(loader):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            logits = model(images)
            probabilities = torch.softmax(logits, dim=1)
            scores, indices = probabilities.topk(5, dim=1)

            predictions = indices[:, 0]
            batch_size = labels.size(0)

            for i in range(batch_size):
                actual = int(labels[i].item())
                predicted = int(predictions[i].item())
                confidence = float(scores[i, 0].item())
                top5_indices = indices[i].tolist()
                top5_scores = scores[i].tolist()
                is_correct = actual == predicted
                is_top5 = actual in top5_indices

                processed += 1
                correct1 += int(is_correct)
                correct5 += int(is_top5)
                class_total[actual] += 1
                class_correct[actual] += int(is_correct)
                class_top5[actual] += int(is_top5)
                confusion[actual][predicted] += 1

                top5_text = ";".join(
                    f"{classes[k]}:{v:.6f}"
                    for k, v in zip(top5_indices, top5_scores)
                )

                row = {
                    "image": paths[i],
                    "actual": classes[actual],
                    "predicted": classes[predicted],
                    "confidence": f"{confidence:.8f}",
                    "correct": is_correct,
                    "actual_in_top5": is_top5,
                    "top5_predictions": top5_text,
                }
                prediction_rows.append(row)

                if not is_correct:
                    pair_counts[(classes[actual], classes[predicted])] += 1
                    error_rows.append(row)

            if (batch_index + 1) % 100 == 0:
                print(f"Processed {processed}/{len(dataset)} images")

    elapsed = time.time() - started

    per_class_rows = []
    for i, name in enumerate(classes):
        total = class_total[i]
        per_class_rows.append({
            "class": name,
            "test_images": total,
            "correct_predictions": class_correct[i],
            "top1_accuracy": f"{class_correct[i] / total:.6f}" if total else "0",
            "top5_accuracy": f"{class_top5[i] / total:.6f}" if total else "0",
            "errors": total - class_correct[i],
        })

    pair_rows = [
        {"actual": actual, "predicted": predicted, "count": count}
        for (actual, predicted), count in sorted(
            pair_counts.items(), key=lambda item: item[1], reverse=True
        )
    ]

    high_confidence_errors = [
        row for row in error_rows
        if float(row["confidence"]) >= args.high_confidence
    ]

    write_csv(
        output / "all_predictions.csv",
        prediction_rows,
        ["image", "actual", "predicted", "confidence",
         "correct", "actual_in_top5", "top5_predictions"],
    )
    write_csv(
        output / "misclassified_images.csv",
        error_rows,
        ["image", "actual", "predicted", "confidence",
         "correct", "actual_in_top5", "top5_predictions"],
    )
    write_csv(
        output / "high_confidence_errors.csv",
        high_confidence_errors,
        ["image", "actual", "predicted", "confidence",
         "correct", "actual_in_top5", "top5_predictions"],
    )
    write_csv(
        output / "per_class_metrics.csv",
        per_class_rows,
        ["class", "test_images", "correct_predictions",
         "top1_accuracy", "top5_accuracy", "errors"],
    )
    write_csv(
        output / "confusion_pairs.csv",
        pair_rows,
        ["actual", "predicted", "count"],
    )

    with (output / "confusion_matrix.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(["actual/predicted"] + classes)
        for name, values in zip(classes, confusion):
            writer.writerow([name] + values)

    metrics = {
        "dataset": "Food-101 official test split",
        "expected_images": len(dataset),
        "processed_images": processed,
        "skipped_images": len(dataset) - processed,
        "top1_correct": correct1,
        "top5_correct": correct5,
        "top1_accuracy": correct1 / processed if processed else 0,
        "top5_accuracy": correct5 / processed if processed else 0,
        "misclassified_images": len(error_rows),
        "high_confidence_errors": len(high_confidence_errors),
        "high_confidence_threshold": args.high_confidence,
        "elapsed_seconds": elapsed,
        "average_ms_per_image": elapsed * 1000 / processed if processed else 0,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "class_count": class_count,
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    # HTML gallery links directly to original dataset images.
    gallery = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>FoodInsightAI - Model Error Gallery</title>",
        "<style>body{font:15px Arial;margin:24px;background:#f5f6f8;color:#222}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}"
        "article{background:white;padding:12px;border-radius:10px;box-shadow:0 1px 5px #ddd}"
        "img{width:100%;height:190px;object-fit:cover;border-radius:6px}"
        ".bad{color:#b42318;font-weight:bold}.muted{color:#666;font-size:13px}"
        "</style></head><body>",
        "<h1>FoodInsightAI - Misclassification Gallery</h1>",
        f"<p>{len(error_rows)} incorrect predictions from {processed} test images.</p>",
        "<div class='grid'>",
    ]

    for row in error_rows:
        relative = Path(row["image"]).relative_to(data_root.parent)
        image_link = "../../" + relative.as_posix()
        gallery.append(
            "<article>"
            f"<a href='{html.escape(image_link)}' target='_blank'>"
            f"<img loading='lazy' src='{html.escape(image_link)}'></a>"
            f"<p>Actual: <b>{html.escape(row['actual'])}</b></p>"
            f"<p class='bad'>Predicted: {html.escape(row['predicted'])}</p>"
            f"<p>Confidence: {float(row['confidence']):.2%}</p>"
            f"<p class='muted'>Top 5: {html.escape(row['top5_predictions'])}</p>"
            "</article>"
        )

    gallery.extend(["</div></body></html>"])
    (output / "error_gallery.html").write_text(
        "\n".join(gallery), encoding="utf-8"
    )

    print("\n========== EVALUATION COMPLETE ==========")
    print(json.dumps(metrics, indent=2))
    print(f"\nReports saved to: {output}")


if __name__ == "__main__":
    main()
