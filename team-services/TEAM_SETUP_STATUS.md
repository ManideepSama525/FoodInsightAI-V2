# FoodInsightAI team-demo setup (candidate, not yet clean-clone validated)

`Prepare-TeamDemo.ps1` is the first part of a clean-laptop setup, not a complete
one-click installer. It downloads private model assets, creates **new per-laptop**
service credentials and a `.env`, stages verified Sentinel model files, validates
Docker Compose, and optionally prepares the host Python environments and pinned
Qwen weights. It **does not** launch containers or run migrations.

## Prerequisites

- Fresh clone of public `FoodInsightAI-V2`, branch `development`.
- GitHub CLI authenticated as a collaborator on the **private** model-assets repo.
- Docker Desktop with Linux containers and Compose, Python 3.12 launcher (`py`).
- RTX GPU and NVIDIA driver compatible with selected CUDA PyTorch build.
- At least 15 GB free for Qwen weights plus build/cache/dataset overhead;
  practical deployment may need significantly more disk and RAM.

## On a clean teammate laptop only

```powershell
Set-Location C:\path\to\FoodInsightAI-V2
& .\team-services\scripts\Prepare-TeamDemo.ps1 -InstallSentinelDeps -InstallQwenDeps -DownloadQwen
```

If the GPU wheel selected in the script is not available on that Windows/driver
combination, the script stops, rather than silently falling back to CPU. Check
[PyTorch](https://pytorch.org/get-started/locally/) and rerun with a compatible
CUDA-enabled build already installed in `team-services/.qwen-venv`.

The script does not replace an existing `.env` and never copies credentials from
the author's laptop. If an existing `.env` has mismatched or weak tokens, fix
**locally** without sharing its values. Ensure `~/.foodinsightai` is private to
the local user. The generated `.env` must remain Git-ignored.

## Service startup (not yet automated or verified as a full stack)

The following are **separate foreground commands**, best run in distinct
PowerShell windows on the teammate's clean laptop:

```powershell
# Sentinel restricted API (reads SENTINEL_* variables from .env only after
# they are set in this process environment; it does not auto-read .env):
# Set the needed process values privately before this command.
& "$HOME\.foodinsightai\sentinel-venv-312\Scripts\python.exe" .\team-services\sentinel-service\backend\run_local.py

# Qwen3-4B base 4-bit, localhost:8023 (this takes several seconds to warm up):
& .\team-services\.qwen-venv\Scripts\python.exe .\team-services\qwen_service\run_service.py --serve

# Full CPU services + main backend/frontend/Neo4j (requires tested migration/data bootstrap):
docker compose -f docker-compose.yml -f team-services/docker-compose.models.override.yml up -d --build
```

The Sentinel command must be run with the same `SENTINEL_INGEST_TOKEN` set in
Docker `.env`; otherwise ingestion correctly fails. This is a known gap in the
starter instructions until the full launch wrapper is created and tested.

## Incomplete deployment requirements

1. Source commit/push of `team-services` and a clean clone from the published
   commit.
2. Fresh-laptop installation and live authenticated backend-to-Qwen recipe test.
3. Sentinel startup with the exact per-laptop `.env` tokens (no secrets in logs).
4. SQLite migration/seed verification, recipe/USDA/IFCT data and Neo4j graph
   bootstrap, regulatory evidence availability and full frontend flows.
5. Tested shutdown/recovery and GPU/VRAM differences across teammates.

Model-only smoke tests have passed on the author's laptop, not these complete
app conditions. Keep ports 3000, 8000, 8010, 8023 and Neo4j bound to localhost;
never expose the restricted Sentinel demo to the public internet. Do not
publish `.pkl` or `.joblib` to Git or load unverified model files.
