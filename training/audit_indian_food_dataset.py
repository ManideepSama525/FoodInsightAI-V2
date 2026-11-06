import os, glob, json, hashlib, csv, io, collections
import pyarrow.parquet as pq
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = False

ROOT = "/workspace/data/indian_food/raw"
OUT = "/workspace/artifacts/indian_food_audit"
os.makedirs(OUT, exist_ok=True)

classes = {
    0:"biryani", 1:"cholebhature", 2:"dabeli", 3:"dal", 4:"dhokla",
    5:"dosa", 6:"jalebi", 7:"kathiroll", 8:"kofta", 9:"naan",
    10:"pakora", 11:"paneer", 12:"panipuri", 13:"pavbhaji", 14:"vadapav"
}

files = sorted(glob.glob(os.path.join(ROOT, "*.parquet")))
if len(files) != 3:
    raise RuntimeError(f"Expected 3 Parquet files; found {len(files)}")

summary = {
    "total_records": 0,
    "valid_images": 0,
    "corrupt_images": 0,
    "missing_payloads": 0,
    "duplicate_records_after_first_occurrence": 0,
    "unique_image_hashes": 0,
    "formats": {},
    "dimensions": {},
    "splits": {},
    "classes": {},
}
hash_first = {}
rows = []

for path in files:
    name = os.path.basename(path)
    split = "test" if name.startswith("test") else "train"
    print(f"Auditing {name}", flush=True)
    pf = pq.ParquetFile(path)
    split_counts = collections.Counter()

    for batch in pf.iter_batches(batch_size=32, columns=["image", "label"]):
        for record in batch.to_pylist():
            summary["total_records"] += 1
            label = record["label"]
            image_obj = record["image"] or {}
            payload = image_obj.get("bytes")
            split_counts[label] += 1

            item = {
                "split": split,
                "label_id": label,
                "class_name": classes.get(label, "UNKNOWN"),
                "path": image_obj.get("path"),
                "status": "valid",
                "format": None,
                "width": None,
                "height": None,
                "sha256": None,
                "duplicate_of": None,
            }

            if not payload:
                item["status"] = "missing_payload"
                summary["missing_payloads"] += 1
            else:
                digest = hashlib.sha256(payload).hexdigest()
                item["sha256"] = digest

                if digest in hash_first:
                    item["duplicate_of"] = hash_first[digest]
                    summary["duplicate_records_after_first_occurrence"] += 1
                else:
                    hash_first[digest] = f"{split}:{item['class_name']}:{item['path']}"

                try:
                    with Image.open(io.BytesIO(payload)) as im:
                        im.verify()
                    with Image.open(io.BytesIO(payload)) as im:
                        item["format"] = im.format
                        item["width"], item["height"] = im.size

                    summary["valid_images"] += 1
                    summary["formats"][item["format"]] = summary["formats"].get(item["format"], 0) + 1
                    dim = f"{item['width']}x{item['height']}"
                    summary["dimensions"][dim] = summary["dimensions"].get(dim, 0) + 1
                except Exception as exc:
                    item["status"] = "corrupt"
                    item["error"] = str(exc)[:200]
                    summary["corrupt_images"] += 1

            rows.append(item)

    summary["splits"][split] = dict(sorted(split_counts.items()))

    for label, count in split_counts.items():
        key = f"{split}:{classes.get(label, 'UNKNOWN')}"
        summary["classes"][key] = count

    print(f"  {sum(split_counts.values())} records checked", flush=True)

summary["unique_image_hashes"] = len(hash_first)
summary["class_names"] = classes

with open(os.path.join(OUT, "image_audit.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

with open(os.path.join(OUT, "image_audit.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=sorted(set(k for row in rows for k in row)))
    writer.writeheader()
    writer.writerows(rows)

print("\n=== IMAGE AUDIT SUMMARY ===")
print(json.dumps(summary, indent=2))
print(f"\nReports saved to {OUT}")
