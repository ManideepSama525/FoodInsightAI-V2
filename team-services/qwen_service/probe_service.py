"""Loopback smoke test for the authenticated Qwen service (may trigger model generation)."""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8023")
parser.add_argument("--title", default="Vegetable pulao")
args = parser.parse_args()

token_path = Path.home() / ".foodinsightai" / "recipe_service_token.txt"
if not token_path.is_file():
    raise SystemExit("Token file not found: " + str(token_path))
with urllib.request.urlopen(args.url + "/healthz", timeout=10) as response:
    print("HEALTH_HTTP:", response.status)
req = urllib.request.Request(
    args.url + "/generate-recipe",
    data=json.dumps({"title": args.title, "max_new_tokens": 512}).encode("utf-8"),
    headers={"Content-Type":"application/json", "X-Recipe-Service-Token":token_path.read_text(encoding="utf-8").strip()},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=250) as response:
        status, payload = response.status, json.load(response)
except urllib.error.HTTPError as error:
    status = error.code
    payload = json.load(error)
print("GENERATE_HTTP:", status)
print("RESULT:", "PASSED" if status == 200 else "REJECTED_OR_UNAVAILABLE")
print("INGREDIENT_COUNT:", len(payload.get("ingredients", [])))
print("STEP_COUNT:", len(payload.get("steps", [])))
print("DETAIL:", str(payload.get("detail", ""))[:250])
