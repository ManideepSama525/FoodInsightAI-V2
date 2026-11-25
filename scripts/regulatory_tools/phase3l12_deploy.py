"""Phase 3L.12: safe deployment and runtime validation."""
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
REPORT = ROOT / "logs/regulatory_phase3l12_deployment_report.txt"
REGISTRY = ROOT / (
    "data/regulatory/fssai/"
    "bread_draft_requirements_pending_review_v1.json"
)
EXPECTED_SHA = (
    "7bd29281f345973966eed3ea79869545e5775ee8d7f27f0070ef971128f139d2"
)
COMPOSE = [
    "docker", "compose",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.regulatory.yml",
]

messages = ["FOODINSIGHTAI PHASE 3L.12 - DOCKER DEPLOYMENT"]

def log(value):
    value = str(value)
    messages.append(value)
    print(value, flush=True)

def run(label, args, timeout=600):
    log("=== " + label + " ===")
    result = subprocess.run(
        args, cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    log("EXIT_CODE: " + str(result.returncode))
    if output:
        log(output[-2500:])
    if result.returncode:
        raise RuntimeError(label + " failed")
    return result.stdout.strip()

def http_status(url, method="GET", body=None):
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=8
        ) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError):
        return None

try:
    if not REGISTRY.is_file():
        raise RuntimeError("Draft bread registry missing")

    actual_hash = hashlib.sha256(
        REGISTRY.read_bytes()
    ).hexdigest()

    if actual_hash != EXPECTED_SHA:
        raise RuntimeError(
            "Draft bread registry hash changed; deployment blocked"
        )

    log("LOCAL_REGISTRY_SHA256: VERIFIED")

    for file in (
        "docker-compose.yml",
        "docker-compose.regulatory.yml",
        "frontend/src/app/RegulatoryBreadDraftPanel.tsx",
        "backend/app/services/regulatory_bread_draft_calculator.py",
        "backend/app/api/routes/regulatory.py",
    ):
        if not (ROOT / file).is_file():
            raise RuntimeError("Required file missing: " + file)

    run("DOCKER_COMPOSE_CONFIG", COMPOSE + ["config", "-q"], 60)

    run(
        "BUILD_BACKEND_AND_FRONTEND",
        COMPOSE + ["build", "backend", "frontend"],
        1200,
    )

    run(
        "START_UPDATED_SERVICES",
        COMPOSE + ["up", "-d", "--no-build", "backend", "frontend"],
        300,
    )

    container = run(
        "FIND_RUNNING_BACKEND",
        COMPOSE + ["ps", "-q", "backend"],
        30,
    )

    if not container:
        raise RuntimeError("Backend container is not running")

    probe = r'''
import hashlib
import json
from pathlib import Path

from backend.app.services.regulatory_bread_draft_calculator import (
    compare_draft_bread,
)
from backend.app.api.routes.regulatory import (
    regulatory_bread_draft_preview,
)

path = Path(
    "/app/data/regulatory/fssai/"
    "bread_draft_requirements_pending_review_v1.json"
)

expected = "7bd29281f345973966eed3ea79869545e5775ee8d7f27f0070ef971128f139d2"

if not path.is_file():
    raise RuntimeError("DRAFT_REGISTRY_NOT_MOUNTED_IN_BACKEND")

raw = path.read_bytes()
if hashlib.sha256(raw).hexdigest() != expected:
    raise RuntimeError("DRAFT_REGISTRY_HASH_MISMATCH")

registry = json.loads(raw)
assert registry["compliance_rules_enabled"] is False
assert registry["legal_review_complete"] is False
assert len(registry["requirements"]) == 11

for record in registry["requirements"]:
    assert record["rule_enabled"] is False
    result = compare_draft_bread(
        registry, record["product_category"], "80"
    )
    assert result["compliance_verdict"] is None
    assert result["rule_executed"] is False

def assess(bread_type, percent):
    return regulatory_bread_draft_preview(
        user=object(),
        payload={
            "bread_type": bread_type,
            "ingredient_percent": percent,
            "measurement_basis": "100g_flour",
        },
    )

whole = assess("whole_wheat_bread", "75")
below = assess("whole_wheat_bread", "74.99")
missing = assess("honey_bread", None)
multigrain = assess("multigrain_bread", "20")

assert whole["numerical_screening_status"] == (
    "AT_OR_ABOVE_DRAFT_THRESHOLD"
)
assert below["numerical_screening_status"] == (
    "BELOW_DRAFT_THRESHOLD"
)
assert missing["numerical_screening_status"] == "INSUFFICIENT_DATA"
assert multigrain["numerical_screening_status"] == (
    "TRANSITIONAL_PERIOD_REVIEW_REQUIRED"
)

for result in (whole, below, missing, multigrain):
    assert result["compliance_verdict"] is None
    assert result["legal_review_complete"] is False
    assert result["product_facts_verified"] is False
    assert result["rule_executed"] is False

print("BACKEND_REGISTRY_MOUNT: VERIFIED")
print("BACKEND_REGISTRY_HASH: VERIFIED")
print("DRAFT_CATEGORIES: 11")
print("DIRECT_API_RUNTIME_PROBES: 4 PASSED")
print("RULES_ENABLED: 0")
print("LEGAL_VERDICTS_ISSUED: 0")
print("RUNTIME_PROBE: PASSED")
'''

    run(
        "BACKEND_RUNTIME_PROBE",
        ["docker", "exec", "-i", container, "python", "-c", probe],
        120,
    )

    frontend_status = None
    auth_status = None
    for attempt in range(30):
        frontend_status = http_status("http://localhost:3000/")
        auth_status = http_status(
            "http://localhost:8000/api/v1/regulatory/"
            "assessment/bread-draft-preview",
            method="POST",
            body=json.dumps({
                "bread_type": "whole_wheat_bread",
                "ingredient_percent": "75",
                "measurement_basis": "100g_flour",
            }).encode("utf-8"),
        )
        if frontend_status == 200 and auth_status in (401, 403):
            break
        time.sleep(3)

    log("FRONTEND_HTTP_STATUS: " + str(frontend_status))
    log("UNAUTHENTICATED_BREAD_API_STATUS: " + str(auth_status))

    if frontend_status != 200:
        raise RuntimeError("Frontend HTTP smoke test failed")

    if auth_status not in (401, 403):
        raise RuntimeError(
            "Bread draft API authentication check failed"
        )

    log("FRONTEND_HTTP: PASSED")
    log("BREAD_API_AUTHENTICATION: PASSED")
    log("DATABASE_VOLUME_DELETION: NOT_REQUESTED")
    log("LEGAL_COMPLIANCE_VERDICTS: DISABLED")
    log("STATUS: PASSED")
    code = 0

except Exception as exc:
    log("STATUS: FAILED")
    log("ERROR: " + repr(exc))
    code = 1

REPORT.write_text("\n".join(messages), encoding="utf-8")
log("REPORT: " + str(REPORT))
sys.exit(code)
