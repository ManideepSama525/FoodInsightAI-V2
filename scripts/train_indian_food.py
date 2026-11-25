from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageFile
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import datasets, transforms
from torchvision.models import efficientnet_v2_s

ImageFile.LOAD_TRUNCATED_IMAGES = False

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "indian_food" / "processed"
TAXONOMY_PATH = ROOT / "data" / "indian_food" / "manifests" / "indian_food_taxonomy.json"
PRETRAINED_PATH = ROOT / "data" / "torch-cache" / "hub" / "checkpoints" / "efficientnet_v2_s-dd5fe13b.pth"
OUT_DIR = ROOT / "artifacts" / "indian_food_v1"
IMAGE_SIZE = 224
SEED = 42


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


class IndexedImageFolder(Dataset):
    def __init__(self, base: datasets.ImageFolder, indices: list[int], transform):
        self.base = base
        self.indices = indices
        self.transform = transform
        self.classes = base.classes
        self.class_to_idx = base.class_to_idx
        self.targets = [base.samples[i][1] for i in indices]

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, item):
        path, label = self.base.samples[self.indices[item]]
        with Image.open(path) as image:
            image = image.convert("RGB")
        return self.transform(image), label


def make_model(num_classes: int, pretrained_path: Path) -> nn.Module:
    model = efficientnet_v2_s(weights=None)
    state = torch.load(pretrained_path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    if isinstance(state, dict) and "model" in state and isinstance(state["model"], dict):
        state = state["model"]
    state = {k.removeprefix("module."): v for k, v in state.items()}
    # Replace the source model's 1,000-class head with a fresh 15-class head.
    # Drop classifier parameters before loading to avoid tensor-size mismatches.
    state = {k: v for k, v in state.items() if not k.startswith("classifier.")}
    incompatible = model.load_state_dict(state, strict=False)
    unexpected = list(incompatible.unexpected_keys)
    missing = list(incompatible.missing_keys)
    # Only the original 1000-class classifier is expected to differ.
    bad_missing = [k for k in missing if not k.startswith("classifier.")]
    bad_unexpected = [k for k in unexpected if not k.startswith("classifier.")]
    if bad_missing or bad_unexpected:
        raise RuntimeError(
            "Pretrained checkpoint architecture mismatch. "
            f"Unexpected missing={bad_missing[:8]}, unexpected={bad_unexpected[:8]}"
        )
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    return model


def evaluate(model, loader, device, criterion, amp_enabled):
    model.eval()
    total_loss = 0.0
    total = 0
    all_targets, all_probs = [], []
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=amp_enabled):
                logits = model(images)
                loss = criterion(logits, labels)
            probs = torch.softmax(logits.float(), dim=1)
            total_loss += float(loss.item()) * labels.size(0)
            total += labels.size(0)
            all_targets.extend(labels.cpu().tolist())
            all_probs.append(probs.cpu().numpy())
    probs = np.concatenate(all_probs, axis=0)
    preds = probs.argmax(axis=1)
    return {
        "loss": total_loss / max(total, 1),
        "accuracy": float(accuracy_score(all_targets, preds)),
        "macro_f1": float(f1_score(all_targets, preds, average="macro", zero_division=0)),
        "targets": np.asarray(all_targets),
        "probs": probs,
        "predictions": preds,
    }


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    # Scalar temperature fitted only on validation predictions.
    x = torch.tensor(logits, dtype=torch.float64)
    y = torch.tensor(labels, dtype=torch.long)
    log_t = torch.zeros((), dtype=torch.float64, requires_grad=True)
    optimizer = torch.optim.LBFGS([log_t], lr=0.05, max_iter=80)

    def closure():
        optimizer.zero_grad()
        temperature = log_t.exp().clamp(0.05, 20.0)
        loss = nn.functional.cross_entropy(x / temperature, y)
        loss.backward()
        return loss

    optimizer.step(closure)
    return float(log_t.detach().exp().clamp(0.05, 20.0).item())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU is required for this training run.")
    if not PRETRAINED_PATH.is_file():
        raise SystemExit(f"Pretrained weights not found: {PRETRAINED_PATH}")

    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    expected_classes = [x["name"] for x in taxonomy["classes"]]
    seed_everything(SEED)
    device = torch.device("cuda")
    amp_enabled = True
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    train_root = DATA_ROOT / "train"
    test_root = DATA_ROOT / "test"
    train_base = datasets.ImageFolder(train_root)
    test_base = datasets.ImageFolder(test_root)
    if train_base.classes != expected_classes or test_base.classes != expected_classes:
        raise RuntimeError(
            "ImageFolder class order differs from taxonomy. "
            f"taxonomy={expected_classes}, train={train_base.classes}, test={test_base.classes}"
        )

    indices = np.arange(len(train_base.samples))
    labels = np.asarray(train_base.targets)
    train_idx, val_idx = train_test_split(
        indices, test_size=0.15, random_state=SEED, stratify=labels
    )

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.72, 1.0), ratio=(0.85, 1.15)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(12),
        transforms.ColorJitter(brightness=0.18, contrast=0.18, saturation=0.16, hue=0.025),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(IMAGE_SIZE),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    train_ds = IndexedImageFolder(train_base, train_idx.tolist(), train_tf)
    val_ds = IndexedImageFolder(train_base, val_idx.tolist(), eval_tf)
    test_ds = datasets.ImageFolder(test_root, transform=eval_tf)

    counts = Counter(train_ds.targets)
    sample_weights = torch.DoubleTensor([1.0 / counts[y] for y in train_ds.targets])
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)

    loader_args = dict(
        num_workers=args.workers,
        pin_memory=True,
        persistent_workers=args.workers > 0,
    )
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, sampler=sampler, **loader_args)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, **loader_args)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, **loader_args)

    model = make_model(len(expected_classes), PRETRAINED_PATH).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(
        [
            {"params": model.features.parameters(), "lr": 1.0e-5},
            {"params": model.classifier.parameters(), "lr": 2.0e-4},
        ],
        weight_decay=1.0e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=True)

    start_epoch = 0
    best_f1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    history = []
    checkpoint_path = OUT_DIR / "indian_food_best.pt"
    latest_path = OUT_DIR / "indian_food_latest.pt"

    if args.resume and latest_path.exists():
        state = torch.load(latest_path, map_location=device, weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        scaler.load_state_dict(state["scaler"])
        start_epoch = int(state["epoch"])
        best_f1 = float(state["best_macro_f1"])
        best_epoch = int(state["best_epoch"])
        stale_epochs = int(state["stale_epochs"])
        history = state.get("history", [])

    print(f"Device: {torch.cuda.get_device_name(0)}")
    print(f"Classes: {len(expected_classes)} | train={len(train_ds)} val={len(val_ds)} test={len(test_ds)}")
    print(f"Class order: {expected_classes}")
    print(f"Batch size: {args.batch_size} | epochs={args.epochs} | AMP=True")

    for epoch in range(start_epoch, args.epochs):
        model.train()
        epoch_loss = 0.0
        seen = 0
        started = time.time()
        for batch_no, (images, labels_batch) in enumerate(train_loader, start=1):
            images = images.to(device, non_blocking=True)
            labels_batch = labels_batch.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=amp_enabled):
                logits = model(images)
                loss = criterion(logits, labels_batch)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            scaler.step(optimizer)
            scaler.update()
            epoch_loss += float(loss.item()) * labels_batch.size(0)
            seen += labels_batch.size(0)
            if batch_no % 50 == 0:
                print(f"epoch {epoch+1}/{args.epochs} batch {batch_no}/{len(train_loader)}", flush=True)

        scheduler.step()
        val = evaluate(model, val_loader, device, criterion, amp_enabled)
        record = {
            "epoch": epoch + 1,
            "train_loss": epoch_loss / max(seen, 1),
            "validation_loss": val["loss"],
            "validation_accuracy": val["accuracy"],
            "validation_macro_f1": val["macro_f1"],
            "seconds": round(time.time() - started, 2),
            "learning_rates": [group["lr"] for group in optimizer.param_groups],
        }
        history.append(record)
        print(json.dumps(record), flush=True)

        improved = val["macro_f1"] > best_f1
        if improved:
            best_f1 = val["macro_f1"]
            best_epoch = epoch + 1
            stale_epochs = 0
            torch.save(
                {
                    "model": model.state_dict(),
                    "classes": expected_classes,
                    "taxonomy_version": taxonomy["taxonomy_version"],
                    "epoch": best_epoch,
                    "validation_macro_f1": best_f1,
                    "image_size": IMAGE_SIZE,
                    "seed": SEED,
                },
                checkpoint_path,
            )
        else:
            stale_epochs += 1

        torch.save(
            {
                "epoch": epoch + 1,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "scaler": scaler.state_dict(),
                "best_macro_f1": best_f1,
                "best_epoch": best_epoch,
                "stale_epochs": stale_epochs,
                "history": history,
            },
            latest_path,
        )
        if stale_epochs >= args.patience:
            print(f"Early stopping after {args.patience} non-improving epochs.")
            break

    (OUT_DIR / "training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")

    # Final test evaluation: best validation checkpoint only.
    best_state = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(best_state["model"])
    val = evaluate(model, val_loader, device, criterion, amp_enabled)
    test = evaluate(model, test_loader, device, criterion, amp_enabled)

    # Fit calibration on validation only; test is used only to report final metrics.
    model.eval()
    val_logits = []
    val_labels = []
    with torch.inference_mode():
        for images, labels_batch in val_loader:
            images = images.to(device)
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(images)
            val_logits.append(logits.float().cpu().numpy())
            val_labels.extend(labels_batch.numpy().tolist())
    temperature = fit_temperature(np.concatenate(val_logits), np.asarray(val_labels))

    test_probs = test["probs"]
    calibrated_probs = torch.softmax(
        torch.tensor(np.log(np.clip(test_probs, 1e-12, 1.0)), dtype=torch.float64) / temperature,
        dim=1,
    ).numpy()
    test_preds = calibrated_probs.argmax(axis=1)
    labels_order = list(range(len(expected_classes)))

    report = classification_report(
        test["targets"], test_preds, labels=labels_order, target_names=expected_classes,
        output_dict=True, zero_division=0,
    )
    cm = confusion_matrix(test["targets"], test_preds, labels=labels_order)
    np.savetxt(OUT_DIR / "test_confusion_matrix.csv", cm, delimiter=",", fmt="%d")
    with (OUT_DIR / "test_classification_report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["class", "precision", "recall", "f1-score", "support"])
        writer.writeheader()
        for name in expected_classes:
            row = report[name]
            writer.writerow({
                "class": name,
                "precision": row["precision"],
                "recall": row["recall"],
                "f1-score": row["f1-score"],
                "support": row["support"],
            })

    # Export deterministic inference graph using the exact preprocessing normalization.
    model_cpu = model.to("cpu").eval()
    example = torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    traced = torch.jit.trace(model_cpu, example, strict=False)
    traced.save(str(OUT_DIR / "indian_food_classifier.ts"))

    (OUT_DIR / "classes.json").write_text(json.dumps(expected_classes, indent=2), encoding="utf-8")
    metadata = {
        "model_name": "FoodInsightAI Indian Food EfficientNetV2-S",
        "model_version": "indian-food-v1",
        "architecture": "EfficientNetV2-S",
        "pretrained_weights": str(PRETRAINED_PATH.relative_to(ROOT)),
        "dataset": "bharat-raghunathan/indian-foods-dataset",
        "taxonomy_version": taxonomy["taxonomy_version"],
        "classes": expected_classes,
        "image_size": IMAGE_SIZE,
        "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
        "temperature": temperature,
        "best_epoch": best_epoch,
        "validation_macro_f1": best_f1,
        "test_accuracy": float(accuracy_score(test["targets"], test_preds)),
        "test_macro_f1": float(f1_score(test["targets"], test_preds, average="macro", zero_division=0)),
        "test_top5_accuracy": float(np.mean([
            target in np.argsort(row)[-5:] for target, row in zip(test["targets"], calibrated_probs)
        ])),
        "train_samples": len(train_ds),
        "validation_samples": len(val_ds),
        "test_samples": len(test_ds),
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "torchvision_version": __import__("torchvision").__version__,
        "seed": SEED,
        "test_split_used_for_model_selection": False,
        "dataset_image_rights_note": (
            "Dataset declares CC0-1.0; source README reports Google Images collection. "
            "Individual image rights have not been independently verified."
        ),
    }
    (OUT_DIR / "evaluation_metrics.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("\nFINAL TEST METRICS")
    print(json.dumps(metadata, indent=2))
    print(f"\nArtifacts saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
