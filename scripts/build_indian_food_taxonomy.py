import json
from pathlib import Path

root = Path("/workspace/data/indian_food")
out = root / "manifests"
out.mkdir(parents=True, exist_ok=True)

classes = [
    {"id": 0, "name": "biryani", "category": "rice_dishes"},
    {"id": 1, "name": "cholebhature", "category": "street_food"},
    {"id": 2, "name": "dabeli", "category": "street_food"},
    {"id": 3, "name": "dal", "category": "curries_and_lentils"},
    {"id": 4, "name": "dhokla", "category": "snacks"},
    {"id": 5, "name": "dosa", "category": "south_indian"},
    {"id": 6, "name": "jalebi", "category": "desserts"},
    {"id": 7, "name": "kathiroll", "category": "street_food"},
    {"id": 8, "name": "kofta", "category": "curries_and_lentils"},
    {"id": 9, "name": "naan", "category": "breads"},
    {"id": 10, "name": "pakora", "category": "snacks"},
    {"id": 11, "name": "paneer", "category": "curries_and_lentils"},
    {"id": 12, "name": "panipuri", "category": "street_food"},
    {"id": 13, "name": "pavbhaji", "category": "street_food"},
    {"id": 14, "name": "vadapav", "category": "street_food"},
]

taxonomy = {
    "taxonomy_version": "1.0.0",
    "dataset": "bharat-raghunathan/indian-foods-dataset",
    "model_family": "indian_food_classifier",
    "num_classes": len(classes),
    "classes": classes,
    "categories": sorted(set(c["category"] for c in classes)),
    "food101_merge_policy": "Keep Indian classifier separate until label compatibility and joint evaluation are established.",
    "license": {
        "declared": "CC0-1.0",
        "image_provenance": "Google Images scraping, as stated in the dataset README.",
        "rights_status": "Underlying image-level rights not independently verified."
    }
}

(out / "indian_food_taxonomy.json").write_text(
    json.dumps(taxonomy, indent=2), encoding="utf-8"
)

(out / "indian_food_classes.json").write_text(
    json.dumps([c["name"] for c in classes], indent=2), encoding="utf-8"
)

readme = """# Indian Food Recognition Dataset

## Prepared dataset

- Source: bharat-raghunathan/indian-foods-dataset
- Original records: 4,770
- Clean training images: 3,293
- Clean test images: 751
- Classes: 15
- Exact train/test hash overlap: 0
- Corrupt records: 0

## Class taxonomy

See `indian_food_taxonomy.json` for class IDs, names and broad food categories.

## Directory structure

- `raw/`: original Parquet source files
- `processed/train/`: deduplicated training images
- `processed/test/`: deduplicated test images
- `manifests/`: audit reports, splits and taxonomy

## Evaluation policy

The test split excludes exact image hashes present in training.
Do not use the test split for training, tuning or model selection.

## Provenance and licensing

The source dataset declares CC0-1.0. Its README states that images
were collected through Google Images scraping. Individual image
copyright and reuse permissions have not been independently verified.
Do not redistribute these images or use them in a commercial release
until rights have been reviewed.

## Model policy

Train and evaluate this 15-class Indian food model independently
from the existing 101-class Food-101 model. Consider model merging
only after label compatibility and independent evaluation.
"""

(out / "README.md").write_text(readme, encoding="utf-8")

print("Created Indian food taxonomy and dataset documentation.")
print("Classes:", len(classes))
print("Categories:", taxonomy["categories"])
print("Output:", out)
