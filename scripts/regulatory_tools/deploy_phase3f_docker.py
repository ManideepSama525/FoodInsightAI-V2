from pathlib import Path
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

root = Path.cwd()
report = root / "logs/regulatory_phase3f_deployment_report.txt"
override = root / "docker-compose.regulatory.yml"
registry = root / "data/regulatory/fssai/labelling_amendments_consolidated_v1.json"

lines = ["FOODINSIGHTAI PHASE 3F - DOCKER DEPLOYMENT"]
created_override = False
deployed = False

def note(value):
    lines.append(str(value))
    print(value, flush=True)

def save():
    report.write_text("\n".join(lines), encoding="utf-8")

def fail(message):
    note("STATUS: FAILED")
    note("ERROR: " + str(message))
    if created_override and not deployed:
        override.unlink(missing_ok=True)
        note("NEW_OVERRIDE_REMOVED: YES")
    note("EXISTING_DOCKER_VOLUMES_DELETED: NO")
    save()
    sys.exit(1)

def command(label, args, timeout=600):
    note("")
    note("=== " + label + " ===")
    try:
        result = subprocess.run(
            args,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
    except Exception as exc:
        fail(label + ": " + str(exc))

    output = (result.stdout + "\n" + result.stderr).strip()
    lines.append(output[-18000:])
    print(output[-2500:], flush=True)
    note("EXIT_CODE: " + str(result.returncode))

    if result.returncode != 0:
        fail(label + " failed")

    return result.stdout

if not registry.is_file():
    fail("FSSAI registry missing on host")

if not (root / "docker-compose.yml").is_file():
    fail("docker-compose.yml not found")

if override.exists():
    fail(
        "docker-compose.regulatory.yml already exists. "
        "Inspect it before running this installer."
    )

for required in [
    "backend/app/services/regulatory_bread_screening.py",
    "backend/app/services/regulatory_product_screening.py",
    "backend/app/services/regulatory_registry.py",
    "frontend/src/app/RegulatoryCompliancePanel.tsx",
]:
    if not (root / required).is_file():
        fail("Required local source missing: " + required)

base = ["docker", "compose", "-f", "docker-compose.yml"]

services_text = command(
    "CHECK COMPOSE SERVICES",
    base + ["config", "--services"],
    timeout=30
)
services = services_text.splitlines()

for required in ("backend", "frontend"):
    if required not in services:
        fail("Docker Compose service missing: " + required)

# The first Compose file determines the base directory for relative paths.
override.write_text(
    "services:\n"
    "  backend:\n"
    "    volumes:\n"
    "      - ./data/regulatory/fssai:/app/data/regulatory/fssai:ro\n",
    encoding="utf-8"
)
created_override = True

compose = base + ["-f", "docker-compose.regulatory.yml"]

command(
    "VALIDATE COMPOSE CONFIGURATION",
    compose + ["config", "--quiet"],
    timeout=45
)

command(
    "BUILD BACKEND AND FRONTEND IMAGES",
    compose + ["build", "backend", "frontend"],
    timeout=1200
)

validation_code = """
from datetime import date
from pathlib import Path

from backend.app.services.regulatory_registry import load_amendment_registry
from backend.app.services.regulatory_product_screening import screen_product
from backend.app.services.regulatory_bread_screening import screen_bread_facts

registry = load_amendment_registry()
assert len(registry['amendments']) == 6

screening = screen_product('bread', date(2026, 11, 18))
assert screening['compliance_verdict'] is None

bread = screen_bread_facts(
    'whole_wheat_bread', 80, date(2026, 11, 18)
)
assert bread['compliance_verdict'] is None

route = Path('/app/backend/app/api/routes/regulatory.py')
assert route.is_file()
assert 'PHASE_3D_BREAD_FACT_SCREENING' in route.read_text()

print('REGISTRY_LOADED: YES')
print('AMENDMENT_COUNT: 6')
print('PHASE_3C_SCREENING: PASSED')
print('PHASE_3D_BREAD_SCREENING: PASSED')
print('COMPLIANCE_VERDICTS_DISABLED: YES')
"""

command(
    "VALIDATE NEW BACKEND IMAGE",
    compose + [
        "run", "--rm", "--no-deps",
        "--entrypoint", "python",
        "backend", "-c", validation_code
    ],
    timeout=180
)

# Images and registry access are validated before replacing the services.
command(
    "DEPLOY BACKEND AND FRONTEND",
    compose + [
        "up", "-d", "--no-deps",
        "backend", "frontend"
    ],
    timeout=240
)
deployed = True

note("")
note("=== VERIFY RUNNING BACKEND ===")

backend_container = command(
    "FIND BACKEND CONTAINER",
    compose + ["ps", "-q", "backend"],
    timeout=30
).strip()

if not backend_container:
    fail("Backend container not found after deployment")

command(
    "VERIFY LIVE BACKEND REGISTRY",
    [
        "docker", "exec", backend_container,
        "python", "-c", validation_code
    ],
    timeout=60
)

note("")
note("=== VERIFY REGULATORY API ROUTES ===")

endpoints = [
    (
        "GET",
        "/regulatory/amendments/status?as_of=2026-11-18",
        None,
    ),
    (
        "POST",
        "/regulatory/assessment/preview",
        {
            "product_type": "bread",
            "assessment_date": "2026-11-18",
        },
    ),
    (
        "POST",
        "/regulatory/assessment/bread-facts-preview",
        {
            "bread_type": "whole_wheat_bread",
            "assessment_date": "2026-11-18",
            "whole_wheat_flour_percent": 80,
        },
    ),
]

for method, endpoint, payload in endpoints:
    url = "http://localhost:8000/api/v1" + endpoint
    data = (
        json.dumps(payload).encode("utf-8")
        if payload is not None else None
    )

    status = None
    for attempt in range(20):
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
            continue

        if status in (401, 403):
            break
        if status in (502, 503):
            time.sleep(2)
            continue
        break

    note(method + " " + endpoint + ": HTTP " + str(status))

    if status not in (401, 403):
        fail(
            "Expected authentication enforcement on " +
            endpoint + "; received " + str(status)
        )

note("")
note("STATUS: PASSED")
note("BACKEND_IMAGE: UPDATED")
note("FRONTEND_IMAGE: UPDATED")
note("FSSAI_REGISTRY_MOUNT: READ_ONLY")
note("REGULATORY_API_ROUTES: PRESENT_AND_AUTH_PROTECTED")
note("AUTHENTICATED_BROWSER_ASSESSMENT: NOT_YET_TESTED")
note("DATABASE_MIGRATIONS: NONE")
note("DOCKER_VOLUMES_DELETED: NO")
note("COMPLIANCE_VERDICTS: DISABLED")
note("OVERRIDE_FILE: " + str(override))
save()
note("REPORT: " + str(report))
