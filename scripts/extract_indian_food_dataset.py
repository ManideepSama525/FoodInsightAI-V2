import csv
import hashlib
import json
from pathlib import Path
from io import BytesIO

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path("/workspace/data/indian_food")
RAW = ROOT / "raw"
MANIFESTS = ROOT / "manifests"
PROCESSED = ROOT / "processed"

manifest_files = {
    "train": MANIFESTS / "train_clean.csv",
    "test": MANIFESTS / "test_clean.csv",
}

selected = {}
for split, path in manifest_files.items():
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            selected[(row["shard"], int(row["row_index"]))] = row

written = {"train": 0, "test": 0}
errors = []
verified_hashes = {"train": set(), "test": set()}
shards = sorted(RAW.glob("*.parquet"))

for shard in shards:
    parquet = pq.ParquetFile(shard)
    print(f"Extracting {shard.name}...", flush=True)

    for split in ("train", "test"):
        if not any(key[0] == shard.name for key in selected):
            continue

    offset = 0
    for batch in parquet.iter_batches(batch_size=32, columns=["image", "label"]):
        for row in batch.to_pylist():
            key = (shard.name, offset)
            manifest_row = selected.get(key)

            if manifest_row:
                split = manifest_row["original_split"]
                raw = row["image"]["bytes"]
                digest = hashlib.sha256(raw).hexdigest()

                if digest != manifest_row["sha256"]:
                    errors.append(f"Hash mismatch: {key}")
                else:
                    try:
                        image = Image.open(BytesIO(raw))
                        image.load()
                        label = manifest_row["label"]
                        destination = PROCESSED / split / label
                        destination.mkdir(parents=True, exist_ok=True)
                        output = destination / f"{digest}.jpg"

                        if not output.exists():
                            image.convert("RGB").save(output, format="JPEG", quality=95)

                        verified_hashes[split].add(digest)
                        written[split] += 1
                    except Exception as exc:
                        errors.append(f"Image extraction error {key}: {exc}")

            offset += 1

overlap = verified_hashes["train"] & verified_hashes["test"]

summary = {
    "training_images_extracted": written["train"],
    "test_images_extracted": written["test"],
    "unique_training_hashes": len(verified_hashes["train"]),
    "unique_test_hashes": len(verified_hashes["test"]),
    "train_test_overlap": len(overlap),
    "errors": errors,
    "status": "passed" if not errors and not overlap else "failed",
}

with (MANIFESTS / "extraction_report.json").open("w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("\n========== EXTRACTION REPORT ==========")
print(json.dumps(summary, indent=2))
