import csv
import hashlib
import json
import urllib.request
from pathlib import Path
from collections import Counter
from io import BytesIO

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path("/workspace/data/indian_food")
RAW = ROOT / "raw"
OUT = ROOT / "manifests"
BASE = "https://huggingface.co/datasets/bharat-raghunathan/indian-foods-dataset/resolve/main/"

FILES = {
    "train": [
        "data/train-00000-of-00002-5de00600cb70f0ee.parquet",
        "data/train-00001-of-00002-7cca688335b50fc2.parquet",
    ],
    "test": [
        "data/test-00000-of-00001-75236f054535aed8.parquet",
    ],
}

LABELS = [
    "biryani", "cholebhature", "dabeli", "dal", "dhokla",
    "dosa", "jalebi", "kathiroll", "kofta", "naan",
    "pakora", "paneer", "panipuri", "pavbhaji", "vadapav",
]

records = []
invalid = []
seen_train = set()
seen_test = set()
train_counts = Counter()
test_counts = Counter()

for split, shards in FILES.items():
    for shard_index, relative_path in enumerate(shards):
        filename = relative_path.split("/")[-1]
        local_path = RAW / filename

        if not local_path.exists():
            url = BASE + relative_path
            print(f"Downloading {filename}...", flush=True)
            urllib.request.urlretrieve(url, local_path)

        print(f"Reading {filename}...", flush=True)
        parquet = pq.ParquetFile(local_path)
        row_offset = 0

        for batch in parquet.iter_batches(batch_size=32, columns=["image", "label"]):
            for row in batch.to_pylist():
                label_id = int(row["label"])
                raw = row["image"]["bytes"]
                digest = hashlib.sha256(raw).hexdigest()

                try:
                    image = Image.open(BytesIO(raw))
                    image.verify()
                    image = Image.open(BytesIO(raw))
                    width, height = image.size
                except Exception as exc:
                    invalid.append({
                        "split": split,
                        "shard": filename,
                        "row": row_offset,
                        "error": str(exc)[:200],
                    })
                    row_offset += 1
                    continue

                if label_id < 0 or label_id >= len(LABELS):
                    invalid.append({
                        "split": split,
                        "shard": filename,
                        "row": row_offset,
                        "error": f"Invalid label ID: {label_id}",
                    })
                    row_offset += 1
                    continue

                label = LABELS[label_id]
                keep = False
                reason = ""

                if split == "train":
                    if digest in seen_train:
                        reason = "duplicate_within_train"
                    else:
                        seen_train.add(digest)
                        keep = True
                        train_counts[label] += 1
                else:
                    if digest in seen_train:
                        reason = "duplicate_of_training_image"
                    elif digest in seen_test:
                        reason = "duplicate_within_test"
                    else:
                        seen_test.add(digest)
                        keep = True
                        test_counts[label] += 1

                records.append({
                    "original_split": split,
                    "shard": filename,
                    "row_index": row_offset,
                    "label_id": label_id,
                    "label": label,
                    "sha256": digest,
                    "width": width,
                    "height": height,
                    "status": "included" if keep else "excluded",
                    "exclusion_reason": reason,
                })
                row_offset += 1

for split, output_name in [
    ("train", "train_clean.csv"),
    ("test", "test_clean.csv"),
]:
    selected = [
        r for r in records
        if r["original_split"] == split and r["status"] == "included"
    ]
    with (OUT / output_name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(selected)

with (OUT / "full_audit.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
    writer.writeheader()
    writer.writerows(records)

with (OUT / "invalid_records.json").open("w", encoding="utf-8") as handle:
    json.dump(invalid, handle, indent=2)

summary = {
    "dataset": "bharat-raghunathan/indian-foods-dataset",
    "declared_license": "CC0-1.0",
    "image_provenance": "Dataset README states images were collected through Google Images scraping; individual image rights are not independently verified.",
    "labels": LABELS,
    "original_records": len(records) + len(invalid),
    "valid_records": len(records),
    "invalid_records": len(invalid),
    "clean_train_images": sum(train_counts.values()),
    "clean_test_images": sum(test_counts.values()),
    "train_class_counts": dict(train_counts),
    "test_class_counts": dict(test_counts),
    "train_manifest": "train_clean.csv",
    "test_manifest": "test_clean.csv",
    "audit_manifest": "full_audit.csv",
    "test_policy": "Exact hashes present in training are excluded from test; repeated test hashes are deduplicated.",
}
with (OUT / "audit_summary.json").open("w", encoding="utf-8") as handle:
    json.dump(summary, handle, indent=2)

print("\n========== CLEAN DATASET SUMMARY ==========")
print(json.dumps(summary, indent=2))
print("\nOriginal Parquet files preserved in:", RAW)
print("Manifests saved in:", OUT)
