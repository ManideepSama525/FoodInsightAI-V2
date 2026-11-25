# FoodInsightAI Team Services v3 — candidate package

This is a **source-reviewed candidate**, not yet proven on a clean RTX teammate laptop.
Recoveries: Qwen, freshness and ToxiFruit service sources from the running project.
Sentinel-XDR, application data and full installer are NOT included.

## Recommended layout

Extract the archive so the files land at `FOODINSIGHTAI_REPO/team-services/`:

```
FoodInsightAI-V2/
  docker-compose.yml
  team-services/
    docker-compose.models.override.yml
    freshness-service/
    toxifruit-service/
    qwen_service/
    scripts/
  artifacts/        # private model release populated by script
  freshness/outputs/freshness_v1/best_model.pt
  toxifruit/outputs/food_fraud_toxifruit_vegetable_grouped_letterbox_v2/best_model.pt
  model_cache/Qwen3-4B/  # official snapshot, downloaded separately
```

## Recover private model assets (requires GitHub CLI and authorized team collaborator)

From PowerShell, in the repository root:

```powershell
& .\team-services\scripts\Install-ModelAssets.ps1
```

This downloads the exact `team-demo-models-v1` archive, verifies its SHA-256,
verifies all 11 inner files using `model_checksums.csv` and refuses to overwrite
nonmatching existing files. No trained model is committed to Git.

## CPU model containers: dry-run validation FIRST

```powershell
& .\team-services\scripts\Test-ModelServices.ps1
```

After inspecting the compose output, **on a clean teammate installation only**:

```powershell
docker compose -f docker-compose.yml -f team-services/docker-compose.models.override.yml build freshness toxifruit
docker compose -f docker-compose.yml -f team-services/docker-compose.models.override.yml up -d freshness toxifruit
```

The Dockerfiles deliberately do **not** embed the ~250 MB checkpoints; the compose
overlay mounts verified checkpoint files read-only. Existing host models and current
running containers should **not** be changed for this trial.

## Qwen3-4B (GPU, host Python)

Original tested environment on author's laptop (not yet reproducibility-tested):
`torch 2.14.1+cu130`, `transformers 5.19.0`, `bitsandbytes 0.50.2`,
`accelerate 1.15.0`, `peft 0.21.3`, with Python 3.12 and CUDA GPU.
Your teammate needs an appropriate GPU/CUDA-compatible PyTorch wheel.

1. Install Python 3.12 and create an isolated virtual environment at
   `team-services/.qwen-venv`.
2. Install CUDA-compatible `torch` for the RTX GPU, then install
   `team-services/qwen_service/requirements-qwen.txt`.
3. Using the venv Python, download the pinned upstream weights:

```powershell
Set-Location .\team-services
& .\.qwen-venv\Scripts\python.exe -m qwen_service.download_qwen
Set-Location ..
```

This action downloads several gigabytes from the official pinned model revision.

4. Preflight and serve (from project root):

```powershell
py -3.12 .\team-services\qwen_service\run_service.py --check
py -3.12 .\team-services\qwen_service\run_service.py --serve
```

`--check` verifies local model shards, required modules, GPU and selected Python
packages. The service uses **base Qwen3-4B in 4-bit**, with no LoRA adapter.
The token is saved to `%USERPROFILE%\.foodinsightai\recipe_service_token.txt`
outside the Git checkout; it is not printed or packaged.
By default the service binds only to `127.0.0.1:8023` and authenticates
`POST /generate-recipe` using the `X-Recipe-Service-Token` header.

**Backend Docker access via `host.docker.internal` is NOT validated by this kit.**
Do not expose the model to the LAN as a workaround without tightly restricting
firewall access and testing the authenticated backend proxy. Existing host
bridge tokens must be configured per laptop; never copy the developer token.

## Limitations / security

- No DB/Neo4j initialization, regulatory evidence, frontend/backend Docker build
  verification, or Sentinel packaging here. These are still required for a
  genuine one-command team installer.
- `.pt` and `.pkl` files can deserialize executable payloads; download
  only trusted assets with matching published SHA-256 checksums.
- Visual freshness/ToxiFruit classifications are screening estimates, not proof
  of food safety or chemical detection.
- Avoid changing the author's running Docker deployment with this candidate.
