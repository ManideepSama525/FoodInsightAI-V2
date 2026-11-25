import csv
import re
from pathlib import Path
from difflib import SequenceMatcher

root = Path.cwd()
candidate_path = root / "reports/dish_recipe_review/FoodInsightAI_DishRecipe_Candidate_Review/dish_recipe_candidate_review.csv"
source_path = root / "data/indian_recipes_source/Dataset/IndianFoodDatasetCSV.csv"

if not candidate_path.exists():
    matches = list((root / "reports").rglob("dish_recipe_candidate_review.csv"))
    if len(matches) != 1:
        raise SystemExit(f"Expected one candidate CSV; found {len(matches)}")
    candidate_path = matches[0]

if not source_path.exists():
    raise SystemExit(f"Original recipe dataset not found: {source_path}")

with candidate_path.open("r", encoding="utf-8-sig", newline="") as f:
    candidates = list(csv.DictReader(f))

with source_path.open("r", encoding="utf-8-sig", newline="") as f:
    source_rows = list(csv.DictReader(f))

source_by_id = {
    str(row.get("Srno", "")).strip(): row
    for row in source_rows
    if str(row.get("Srno", "")).strip()
}

enriched = []
for candidate in candidates:
    row_id = str(candidate["source_row_number"]).strip()
    source = source_by_id.get(row_id)

    item = dict(candidate)
    if source:
        item.update({
            "original_recipe_name": source.get("RecipeName", ""),
            "translated_recipe_name": source.get("TranslatedRecipeName", ""),
            "original_ingredients": source.get("Ingredients", ""),
            "translated_ingredients": source.get("TranslatedIngredients", ""),
            "instructions": source.get("TranslatedInstructions", "") or source.get("Instructions", ""),
            "source_url": source.get("URL", ""),
            "source_record_found": "yes",
        })
    else:
        item.update({
            "original_recipe_name": "",
            "translated_recipe_name": "",
            "original_ingredients": "",
            "translated_ingredients": "",
            "instructions": "",
            "source_url": "",
            "source_record_found": "no",
        })
    enriched.append(item)

output_dir = root / "reports/dish_recipe_review"
output_dir.mkdir(parents=True, exist_ok=True)

enriched_path = output_dir / "dish_recipe_candidate_evidence.csv"
fields = list(enriched[0].keys()) if enriched else []
with enriched_path.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(enriched)

def normalize(value):
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))

kathi_ids = ["685", "9868"]
kathi = [source_by_id.get(x) for x in kathi_ids]

comparison_path = output_dir / "kathi_roll_duplicate_comparison.txt"
with comparison_path.open("w", encoding="utf-8") as f:
    f.write("CHICKEN KATHI ROLL SOURCE RECORD COMPARISON\n")
    f.write("=" * 55 + "\n\n")

    if not all(kathi):
        f.write("One or both source records were not found.\n")
    else:
        for row_id, row in zip(kathi_ids, kathi):
            f.write(f"SOURCE ROW: {row_id}\n")
            f.write(f"RecipeName: {row.get('RecipeName', '')}\n")
            f.write(f"TranslatedRecipeName: {row.get('TranslatedRecipeName', '')}\n")
            f.write(f"URL: {row.get('URL', '')}\n")
            f.write(f"Ingredients: {row.get('TranslatedIngredients', '')}\n")
            f.write(f"Instructions: {row.get('TranslatedInstructions', '')}\n\n")

        ingredients_a = normalize(kathi[0].get("TranslatedIngredients") or kathi[0].get("Ingredients"))
        ingredients_b = normalize(kathi[1].get("TranslatedIngredients") or kathi[1].get("Ingredients"))
        instructions_a = normalize(kathi[0].get("TranslatedInstructions") or kathi[0].get("Instructions"))
        instructions_b = normalize(kathi[1].get("TranslatedInstructions") or kathi[1].get("Instructions"))

        f.write("AUTOMATED COMPARISON (similarity indicators, not a duplicate verdict)\n")
        f.write(f"Ingredient text similarity: {SequenceMatcher(None, ingredients_a, ingredients_b).ratio():.3f}\n")
        f.write(f"Instruction text similarity: {SequenceMatcher(None, instructions_a, instructions_b).ratio():.3f}\n")
        f.write(f"Exact normalized ingredients: {ingredients_a == ingredients_b}\n")
        f.write(f"Exact normalized instructions: {instructions_a == instructions_b}\n")

print({
    "candidate_rows": len(candidates),
    "source_records_found": sum(x["source_record_found"] == "yes" for x in enriched),
    "source_records_missing": sum(x["source_record_found"] == "no" for x in enriched),
    "enriched_csv": str(enriched_path),
    "kathi_comparison": str(comparison_path),
})
