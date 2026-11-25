<# Checks container source layout and compose config WITHOUT building or starting anything. #>
[CmdletBinding()]
param([string]$ProjectRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $ProjectRoot
$compose = Join-Path $ProjectRoot 'docker-compose.yml'
$overlay = Join-Path $ProjectRoot 'team-services\docker-compose.models.override.yml'
foreach ($file in @($compose,$overlay)) { if (!(Test-Path $file)) { throw "Missing compose file: $file" } }
foreach ($rel in @('freshness\outputs\freshness_v1\best_model.pt',
                  'toxifruit\outputs\food_fraud_toxifruit_vegetable_grouped_letterbox_v2\best_model.pt')) {
    if (!(Test-Path (Join-Path $ProjectRoot $rel))) { throw "Missing checkpoint: $rel" }
}
Write-Host "CHECKPOINT_PATHS: VERIFIED"
$null = docker compose -f $compose -f $overlay config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose overlay validation failed' }
Write-Host "DOCKER_COMPOSE_OVERLAY: VALID"
Write-Host 'SAFE_CHECK_COMPLETED: No containers built or started.'
