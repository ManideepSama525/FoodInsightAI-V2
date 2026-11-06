import csv
import html
from pathlib import Path

output = Path("/workspace/artifacts/error_analysis")
csv_path = output / "misclassified_images.csv"
rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))

parts = [
    "<!doctype html><html><head><meta charset='utf-8'>",
    "<meta name='viewport' content='width=device-width,initial-scale=1'>",
    "<title>FoodInsightAI - Misclassification Gallery</title>",
    """<style>
    body{font:15px Arial;margin:24px;background:#f5f6f8;color:#222}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}
    article{background:white;padding:12px;border-radius:10px;box-shadow:0 1px 5px #ddd}
    img{width:100%;height:210px;object-fit:cover;border-radius:6px}
    .bad{color:#b42318;font-weight:bold}.muted{color:#666;font-size:12px;overflow-wrap:anywhere}
    </style></head><body>""",
    "<h1>FoodInsightAI - Misclassification Gallery</h1>",
    f"<p>{len(rows)} incorrect predictions from 25,250 test images.</p>",
    "<div class='grid'>"
]

for row in rows:
    image_path = Path(row["image"].replace("\\", "/"))
    try:
        index = image_path.parts.index("food-101")
        relative_image = Path(*image_path.parts[index:]).as_posix()
    except ValueError:
        continue

    # Gallery is in artifacts/error_analysis; dataset is in data/food101.
    src = "../../data/food101/" + relative_image
    actual = html.escape(row["actual"])
    predicted = html.escape(row["predicted"])
    confidence = float(row["confidence"])
    top5 = html.escape(row["top5_predictions"])

    parts.append(
        f"<article><a href='{src}' target='_blank'>"
        f"<img loading='lazy' src='{src}'></a>"
        f"<p>Actual: <b>{actual}</b></p>"
        f"<p class='bad'>Predicted: {predicted}</p>"
        f"<p>Confidence: {confidence:.2%}</p>"
        f"<p class='muted'>Top 5: {top5}</p></article>"
    )

parts.append("</div></body></html>")
(output / "error_gallery.html").write_text("\n".join(parts), encoding="utf-8")
print(f"Gallery repaired: {len(rows)} cards")
