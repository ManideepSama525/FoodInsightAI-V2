import argparse
import csv
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset, WeightedRandomSampler
from torchvision import datasets, transforms, models

from train_food101 import (
    InferenceCompatibleFit,
    seed_everything,
    train_epoch,
    evaluate,
    save_checkpoint,
)

HARD_CLASSES = {
    "steak", "pork_chop", "chocolate_mousse", "apple_pie",
    "bread_pudding", "ravioli", "foie_gras", "huevos_rancheros",
    "ceviche", "beet_salad", "omelette", "tuna_tartare",
    "scallops", "ice_cream", "filet_mignon",
    "prime_rib", "chocolate_cake", "tiramisu", "beef_tartare",
    "ramen", "pho", "frozen_yogurt", "gnocchi", "baklava",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="/workspace/data/food101")
    parser.add_argument("--artifacts", default="/workspace/artifacts")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=0.00002)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--hard-class-weight", type=float, default=1.5)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required.")

    seed_everything(42)
    torch.backends.cudnn.benchmark = True
    device = torch.device("cuda")

    source = Path(args.artifacts)
    output = source / "food101_v2_fixed"
    output.mkdir(parents=True, exist_ok=True)

    best_source = source / "food101_best_state.pt"
    labels_path = source / "classes.json"
    if not best_source.exists() or not labels_path.exists():
        raise FileNotFoundError("Baseline checkpoint or classes.json missing.")

    classes = json.loads(labels_path.read_text(encoding="utf-8"))
    class_to_idx = {name: i for i, name in enumerate(classes)}

    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.70, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomApply([
            transforms.ColorJitter(
                brightness=0.20, contrast=0.20,
                saturation=0.15, hue=0.025
            )
        ], p=0.7),
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

    data_dir = Path(args.data_dir)
    train_aug = datasets.Food101(
        root=str(data_dir), split="train",
        download=False, transform=train_transform
    )
    train_eval = datasets.Food101(
        root=str(data_dir), split="train",
        download=False, transform=eval_transform
    )

    # Reproduce the original deterministic stratified 90/10 split.
    class_indices = {}
    for index, label in enumerate(train_aug._labels):
        class_indices.setdefault(label, []).append(index)

    rng = random.Random(42)
    train_indices, val_indices = [], []
    for label, indices in class_indices.items():
        indices = indices.copy()
        rng.shuffle(indices)
        val_count = max(1, round(len(indices) * 0.10))
        val_indices.extend(indices[:val_count])
        train_indices.extend(indices[val_count:])

    rng.shuffle(train_indices)
    rng.shuffle(val_indices)

    # Extra sampling exposure for categories identified by baseline errors.
    sample_weights = []
    for index in train_indices:
        label_index = train_aug._labels[index]
        class_name = classes[label_index]
        weight = args.hard_class_weight if class_name in HARD_CLASSES else 1.0
        sample_weights.append(weight)

    sampler = WeightedRandomSampler(
        torch.DoubleTensor(sample_weights),
        num_samples=len(train_indices),
        replacement=True,
    )

    common = {
        "batch_size": args.batch_size,
        "num_workers": args.workers,
        "pin_memory": True,
        "persistent_workers": args.workers > 0,
    }

    train_loader = DataLoader(
        Subset(train_aug, train_indices),
        sampler=sampler, **common
    )
    val_loader = DataLoader(
        Subset(train_eval, val_indices),
        shuffle=False, **common
    )

    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    print(
        f"Training: {len(train_indices)}, validation: {len(val_indices)}, "
        f"classes: {len(classes)}",
        flush=True,
    )
    print("Extra sampling classes:", len(HARD_CLASSES), flush=True)

    # Rebuild exact EfficientNetV2-S architecture and load best baseline weights.
    model = models.efficientnet_v2_s(weights=None)
    model.classifier[1] = nn.Linear(
        model.classifier[1].in_features, len(classes)
    )

    checkpoint = torch.load(
        best_source, map_location="cpu", weights_only=False
    )
    model.load_state_dict(checkpoint["model"], strict=True)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=0.01,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs
    )
    scaler = torch.amp.GradScaler("cuda")

    best_val = float("inf")
    stale = 0
    history = []
    best_path = output / "food101_v2_best.pt"
    latest_path = output / "food101_v2_latest.pt"
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()

        train_metrics = train_epoch(
            model, train_loader, criterion, optimizer, scaler, device
        )
        model.eval()
        val_total = 0
        val_loss_total = 0.0
        val_correct1 = 0
        val_correct5 = 0

        with torch.inference_mode():
            for val_images, val_labels in val_loader:
                val_images = val_images.to(device, non_blocking=True)
                val_labels = val_labels.to(device, non_blocking=True)

                # Validation uses FP32, independently of training AMP.
                val_logits = model(val_images).float()

                if not torch.isfinite(val_logits).all():
                    raise RuntimeError("Non-finite validation logits detected.")

                val_loss = criterion(val_logits, val_labels)

                if not torch.isfinite(val_loss):
                    raise RuntimeError("Non-finite FP32 validation loss detected.")

                count = val_labels.size(0)
                top5 = val_logits.topk(5, dim=1).indices

                val_total += count
                val_loss_total += val_loss.item() * count
                val_correct1 += (val_logits.argmax(1) == val_labels).sum().item()
                val_correct5 += (top5 == val_labels.unsqueeze(1)).any(dim=1).sum().item()

        val_metrics = {
            "loss": val_loss_total / val_total,
            "top1_accuracy": val_correct1 / val_total,
            "top5_accuracy": val_correct5 / val_total,
            "samples": val_total,
        }
        scheduler.step()

        record = {
            "epoch": epoch,
            "train": train_metrics,
            "validation": val_metrics,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "seconds": round(time.time() - epoch_start, 2),
        }
        history.append(record)
        print(json.dumps(record), flush=True)

        if val_metrics["loss"] < best_val:
            best_val = val_metrics["loss"]
            stale = 0
            save_checkpoint(best_path, {
                "model": model.state_dict(),
                "epoch": epoch,
                "best_val": best_val,
                "classes": classes,
            })
        else:
            stale += 1

        save_checkpoint(latest_path, {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "scaler": scaler.state_dict(),
            "epoch": epoch,
            "best_val": best_val,
            "stale_epochs": stale,
            "history": history,
        })

        if stale >= args.patience:
            print("Early stopping.", flush=True)
            break

    # Export the best validation checkpoint, not merely the final epoch.
    best = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(best["model"])
    model.eval()

    scripted = torch.jit.script(model.cpu())
    temporary = output / "food_classifier_v2.ts.tmp"
    scripted.save(str(temporary))
    temporary.replace(output / "food_classifier_v2.ts")

    (output / "classes.json").write_text(
        json.dumps(classes, indent=2), encoding="utf-8"
    )
    (output / "training_history.json").write_text(
        json.dumps(history, indent=2), encoding="utf-8"
    )

    with (output / "training_history.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow([
            "epoch", "train_top1", "train_top5",
            "validation_top1", "validation_top5",
            "validation_loss", "seconds"
        ])
        for item in history:
            writer.writerow([
                item["epoch"],
                item["train"]["top1_accuracy"],
                item["train"]["top5_accuracy"],
                item["validation"]["top1_accuracy"],
                item["validation"]["top5_accuracy"],
                item["validation"]["loss"],
                item["seconds"],
            ])

    print("\n========== FINE-TUNING COMPLETE ==========")
    print("Best validation loss:", best_val)
    print("Best epoch:", best["epoch"])
    print("Elapsed minutes:", round((time.time() - started) / 60, 2))
    print("New model:", output / "food_classifier_v2.ts")
    print("Original model was not modified.")

if __name__ == "__main__":
    main()
