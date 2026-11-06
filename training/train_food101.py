import argparse
import csv
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms, models
from torchvision.models import EfficientNet_V2_S_Weights


class InferenceCompatibleFit:
    """Match the backend's ImageOps.fit preprocessing."""

    def __call__(self, image):
        from PIL import Image, ImageOps
        image = ImageOps.exif_transpose(image).convert("RGB")
        return ImageOps.fit(
            image, (224, 224), method=Image.Resampling.BILINEAR
        )


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_loaders(data_dir, batch_size, workers, seed):
    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.75, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(
            brightness=0.15, contrast=0.15, saturation=0.12
        ),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=(0.485, 0.456, 0.406),
            std=(0.229, 0.224, 0.225),
        ),
    ])

    eval_transform = transforms.Compose([
        InferenceCompatibleFit(),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=(0.485, 0.456, 0.406),
            std=(0.229, 0.224, 0.225),
        ),
    ])

    train_augmented = datasets.Food101(
        root=str(data_dir), split="train",
        download=False, transform=train_transform
    )
    train_eval = datasets.Food101(
        root=str(data_dir), split="train",
        download=False, transform=eval_transform
    )
    test_set = datasets.Food101(
        root=str(data_dir), split="test",
        download=False, transform=eval_transform
    )

    # Stratified 90/10 split: every class contributes to both sets.
    class_indices = {}
    for index, label in enumerate(train_augmented._labels):
        class_indices.setdefault(label, []).append(index)

    rng = random.Random(seed)
    train_indices, val_indices = [], []

    for label, indices in class_indices.items():
        rng.shuffle(indices)
        val_count = max(1, round(len(indices) * 0.10))
        val_indices.extend(indices[:val_count])
        train_indices.extend(indices[val_count:])

    rng.shuffle(train_indices)
    rng.shuffle(val_indices)

    common = {
        "batch_size": batch_size,
        "num_workers": workers,
        "pin_memory": True,
        "persistent_workers": workers > 0,
    }

    return (
        DataLoader(Subset(train_augmented, train_indices),
                   shuffle=True, **common),
        DataLoader(Subset(train_eval, val_indices),
                   shuffle=False, **common),
        DataLoader(test_set, shuffle=False, **common),
        train_augmented.classes,
    )


def train_epoch(model, loader, criterion, optimizer, scaler, device):
    model.train()
    total_loss = 0.0
    total = 0
    correct1 = 0
    correct5 = 0

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)

        with torch.autocast(
            device_type="cuda", dtype=torch.float16,
            enabled=device.type == "cuda"
        ):
            logits = model(images)
            loss = criterion(logits, labels)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        batch = labels.size(0)
        total += batch
        total_loss += loss.item() * batch
        top5 = logits.topk(5, dim=1).indices
        correct1 += (top5[:, 0] == labels).sum().item()
        correct5 += (top5 == labels.unsqueeze(1)).any(dim=1).sum().item()

    return {
        "loss": total_loss / total,
        "top1_accuracy": correct1 / total,
        "top5_accuracy": correct5 / total,
        "samples": total,
    }


@torch.no_grad()
def evaluate(model, loader, criterion, device, class_count):
    model.eval()
    total_loss = 0.0
    total = 0
    correct1 = 0
    correct5 = 0
    confusion = np.zeros((class_count, class_count), dtype=np.int64)

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        with torch.autocast(
            device_type="cuda", dtype=torch.float16,
            enabled=device.type == "cuda"
        ):
            logits = model(images)
            loss = criterion(logits, labels)

        predictions = logits.argmax(dim=1)
        top5 = logits.topk(5, dim=1).indices
        batch = labels.size(0)

        total += batch
        total_loss += loss.item() * batch
        correct1 += (predictions == labels).sum().item()
        correct5 += (top5 == labels.unsqueeze(1)).any(dim=1).sum().item()

        encoded = (
            labels.detach().cpu().numpy() * class_count
            + predictions.detach().cpu().numpy()
        )
        confusion += np.bincount(
            encoded, minlength=class_count * class_count
        ).reshape(class_count, class_count)

    return {
        "loss": total_loss / total,
        "top1_accuracy": correct1 / total,
        "top5_accuracy": correct5 / total,
        "samples": total,
    }, confusion


def save_checkpoint(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, path)


def write_class_reports(artifact_dir, classes, confusion):
    rows = []
    for index, name in enumerate(classes):
        tp = int(confusion[index, index])
        support = int(confusion[index, :].sum())
        predicted = int(confusion[:, index].sum())
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        rows.append({
            "class": name,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "support": support,
        })

    with (artifact_dir / "classification_report.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    np.savetxt(
        artifact_dir / "confusion_matrix.csv",
        confusion, delimiter=",", fmt="%d",
        header="Rows=true class; columns=predicted class",
        comments="",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="/workspace/data/food101")
    parser.add_argument("--artifact-dir", default="/workspace/artifacts")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--learning-rate", type=float, default=0.0001)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required.")

    seed_everything(args.seed)
    torch.backends.cudnn.benchmark = True
    device = torch.device("cuda")

    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    print(
        "VRAM GB:",
        round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2),
        flush=True,
    )

    train_loader, val_loader, test_loader, classes = build_loaders(
        data_dir, args.batch_size, args.workers, args.seed
    )
    print(
        f"Dataset: {len(train_loader.dataset)} train, "
        f"{len(val_loader.dataset)} validation, "
        f"{len(test_loader.dataset)} official test, "
        f"{len(classes)} classes",
        flush=True,
    )

    model = models.efficientnet_v2_s(
        weights=EfficientNet_V2_S_Weights.DEFAULT
    )
    model.classifier[1] = nn.Linear(
        model.classifier[1].in_features, len(classes)
    )
    model = model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=0.01
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs
    )
    scaler = torch.amp.GradScaler("cuda")

    best_path = artifact_dir / "food101_best_state.pt"
    latest_path = artifact_dir / "food101_latest_checkpoint.pt"
    history_path = artifact_dir / "training_history.csv"
    history = []
    start_epoch = 1
    best_val = float("inf")
    stale_epochs = 0
    started = time.time()

    if args.resume:
        if not latest_path.exists():
            raise FileNotFoundError("No latest checkpoint exists to resume.")
        checkpoint = torch.load(
            latest_path, map_location=device, weights_only=False
        )
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scheduler.load_state_dict(checkpoint["scheduler"])
        scaler.load_state_dict(checkpoint["scaler"])
        history = checkpoint["history"]
        start_epoch = checkpoint["epoch"] + 1
        best_val = checkpoint["best_val"]
        stale_epochs = checkpoint["stale_epochs"]
        print("Resuming at epoch", start_epoch, flush=True)

    for epoch in range(start_epoch, args.epochs + 1):
        epoch_start = time.time()
        train_metrics = train_epoch(
            model, train_loader, criterion, optimizer, scaler, device
        )
        val_metrics, _ = evaluate(
            model, val_loader, criterion, device, len(classes)
        )
        scheduler.step()

        record = {
            "epoch": epoch,
            "train": train_metrics,
            "validation": val_metrics,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "epoch_seconds": round(time.time() - epoch_start, 2),
        }
        history.append(record)
        print(json.dumps(record), flush=True)

        improved = val_metrics["loss"] < best_val
        if improved:
            best_val = val_metrics["loss"]
            stale_epochs = 0
            save_checkpoint(best_path, {
                "model": model.state_dict(),
                "epoch": epoch,
                "best_val": best_val,
            })
        else:
            stale_epochs += 1

        save_checkpoint(latest_path, {
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "scaler": scaler.state_dict(),
            "history": history,
            "best_val": best_val,
            "stale_epochs": stale_epochs,
        })

        with history_path.open("w", newline="", encoding="utf-8") as handle:
            fields = [
                "epoch", "train_loss", "train_top1", "train_top5",
                "val_loss", "val_top1", "val_top5", "epoch_seconds",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in history:
                writer.writerow({
                    "epoch": item["epoch"],
                    "train_loss": item["train"]["loss"],
                    "train_top1": item["train"]["top1_accuracy"],
                    "train_top5": item["train"]["top5_accuracy"],
                    "val_loss": item["validation"]["loss"],
                    "val_top1": item["validation"]["top1_accuracy"],
                    "val_top5": item["validation"]["top5_accuracy"],
                    "epoch_seconds": item["epoch_seconds"],
                })

        if stale_epochs >= args.patience:
            print("Early stopping: validation loss did not improve.",
                  flush=True)
            break

    if not best_path.exists():
        raise RuntimeError("No best checkpoint was produced.")

    best_checkpoint = torch.load(
        best_path, map_location=device, weights_only=False
    )
    model.load_state_dict(best_checkpoint["model"])

    # Official test set is used once for final evaluation, not model selection.
    test_metrics, confusion = evaluate(
        model, test_loader, criterion, device, len(classes)
    )
    write_class_reports(artifact_dir, classes, confusion)

    # Export on CPU because the existing application runtime uses CPU inference.
    model = model.to("cpu").eval()
    scripted = torch.jit.trace(
        model, torch.zeros(1, 3, 224, 224)
    )
    scripted = torch.jit.freeze(scripted)
    scripted.save(str(artifact_dir / "food_classifier.ts"))

    (artifact_dir / "classes.json").write_text(
        json.dumps(classes, indent=2), encoding="utf-8"
    )

    report = {
        "dataset": "Food-101",
        "architecture": "EfficientNetV2-S",
        "initial_weights": "ImageNet pretrained",
        "training_method": "Full-network fine-tuning",
        "seed": args.seed,
        "epochs_requested": args.epochs,
        "epochs_completed": len(history),
        "batch_size": args.batch_size,
        "image_size": 224,
        "train_samples": len(train_loader.dataset),
        "validation_samples": len(val_loader.dataset),
        "official_test_samples": len(test_loader.dataset),
        "validation_split": "Stratified 10% from official training split",
        "official_test_used_for_model_selection": False,
        "best_checkpoint_epoch": best_checkpoint["epoch"],
        "history": history,
        "test": test_metrics,
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "total_training_seconds": round(time.time() - started, 2),
    }

    (artifact_dir / "training_metrics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("\nFINAL OFFICIAL TEST METRICS")
    print(json.dumps(test_metrics, indent=2))
    print("Best epoch:", best_checkpoint["epoch"])
    print("Artifacts:", str(artifact_dir), flush=True)


if __name__ == "__main__":
    main()
