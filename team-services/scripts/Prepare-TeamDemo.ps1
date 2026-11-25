<#
FoodInsightAI team-demo preparation. Windows PowerShell 5.1+.
For a clean checkout on a teammate laptop only. No Docker containers started.
Requires GitHub CLI authenticated to the private model release.
#>
[CmdletBinding()]
param(
    [switch]$InstallSentinelDeps,
    [switch]$InstallQwenDeps,
    [switch]$DownloadQwen
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Services = Join-Path $Root 'team-services'
$Gh = Join-Path $HOME 'Tools\GitHubCLI\bin\gh.exe'
$Report = Join-Path $HOME '.foodinsightai\team-demo-prepare-report.txt'
$Records = New-Object 'System.Collections.Generic.List[string]'
function Note([string]$Message) {
    $Records.Add($Message)
    Write-Host $Message
}
function Require-Command([string]$Name) {
    if (!(Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Missing required command: $Name" }
}
function New-DemoSecret {
    $Bytes = New-Object byte[] 48
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
function Require-File([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file absent: $Path" }
}
try {
    Note 'REPORT_TYPE: FOODINSIGHTAI_TEAM_DEMO_PREPARE'
    Require-File (Join-Path $Root 'docker-compose.yml')
    Require-File (Join-Path $Services 'docker-compose.models.override.yml')
    Require-File (Join-Path $Services 'scripts\Install-ModelAssets.ps1')
    Require-File (Join-Path $Services 'sentinel-service\backend\safe_demo_app.py')
    Require-File (Join-Path $Services 'sentinel-service\backend\run_local.py')
    Require-Command 'docker'
    Require-Command 'git'
    Require-Command 'py'
    if (!(Test-Path -LiteralPath $Gh)) {
        $GhCommand = Get-Command gh.exe -ErrorAction SilentlyContinue
        if (!$GhCommand) { throw 'GitHub CLI missing. Install and authenticate it before preparing demo.' }
        $Gh = $GhCommand.Source
    }
    & $Gh auth status 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI is not authenticated.' }
    $IgnoreCheck = & git -C $Root check-ignore .env 2>$null
    if ($LASTEXITCODE -ne 0) { throw '.env is not Git-ignored; refusing to create a credentials file.' }
    Note 'SOURCE_AND_PRIVATE_ACCESS: VERIFIED'

    # Complete, verified private model release; never commit model files to Git.
    & (Join-Path $Services 'scripts\Install-ModelAssets.ps1') -ProjectRoot $Root
    if (!$?) { throw 'Private model asset installation failed.' }
    Note 'PRIVATE_MODEL_RELEASE: INSTALLED_AND_HASH_VERIFIED'

    $SentinelSource = Join-Path $Root 'sentinel\backend\app\ai'
    $SentinelDestination = Join-Path $Services 'sentinel-service\backend\app\ai'
    $Expected = @{
        'model.pkl' = 'BCB0A992DA99918A32DEE9B3F883C52FDC1D925F63E2C1F2943CF162CEA30131'
        'vectorizer.pkl' = '01B67B72EFA1FB361D3796A72A3585B4769407594AD8B955A948A92B420EED1E'
    }
    New-Item -ItemType Directory -Path $SentinelDestination -Force | Out-Null
    foreach ($Name in $Expected.Keys) {
        $Source = Join-Path $SentinelSource $Name
        $Destination = Join-Path $SentinelDestination $Name
        Require-File $Source
        if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne $Expected[$Name]) {
            throw "Untrusted Sentinel model file: $Name"
        }
        if (Test-Path -LiteralPath $Destination) {
            if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Expected[$Name]) {
                throw "Existing Sentinel model does not match private release: $Name"
            }
        } else { Copy-Item -LiteralPath $Source -Destination $Destination }
        $Relative = "team-services/sentinel-service/backend/app/ai/$Name"
        & git -C $Root check-ignore -q $Relative
        if ($LASTEXITCODE -ne 0) { throw "Private Sentinel model is not Git-ignored: $Name" }
    }
    Note 'SENTINEL_MODELS: VERIFIED_AND_GIT_IGNORED'

    # Write credentials only for a fresh demo checkout; never overwrite an existing .env.
    $EnvFile = Join-Path $Root '.env'
    $TokenFile = Join-Path $HOME '.foodinsightai\recipe_service_token.txt'
    if (Test-Path -LiteralPath $EnvFile) {
        Note 'ENV_STATUS: EXISTING_FILE_PRESERVED (verify its tokens match this laptop)'
    } else {
        if (Test-Path -LiteralPath $TokenFile) {
            $RecipeToken = [IO.File]::ReadAllText($TokenFile).Trim()
            if ($RecipeToken.Length -lt 32) { throw 'Existing recipe token too short; no .env created.' }
        } else {
            $RecipeToken = New-DemoSecret
            New-Item -ItemType Directory -Path (Split-Path $TokenFile -Parent) -Force | Out-Null
            [IO.File]::WriteAllText($TokenFile, $RecipeToken, (New-Object System.Text.UTF8Encoding($false)))
        }
        $EnvLines = @(
            '# Local team demo only. Never commit, copy or share this file.',
            'APP_ENV=production',
            'NEO4J_PASSWORD=' + (New-DemoSecret),
            'JWT_SECRET_KEY=' + (New-DemoSecret),
            'SENTINEL_INGEST_TOKEN=' + (New-DemoSecret),
            'SENTINEL_RESPONSE_TOKEN=' + (New-DemoSecret),
            'SENTINEL_ACCOUNT_HASH_KEY=' + (New-DemoSecret),
            'SENTINEL_ANALYST_ACTION_TOKEN=' + (New-DemoSecret),
            'RECIPE_SERVICE_TOKEN=' + $RecipeToken,
            'FOOD_RECIPE_GENERATION_ENABLED=1',
            'FOOD_RECIPE_INFERENCE_URL=http://host.docker.internal:8023'
        )
        [IO.File]::WriteAllLines($EnvFile, $EnvLines, (New-Object System.Text.UTF8Encoding($false)))
        Note 'ENV_STATUS: GENERATED_PRIVATE_PER_LAPTOP_SECRETS (values not logged)'
    }
    $SecretNames = @('NEO4J_PASSWORD','JWT_SECRET_KEY','SENTINEL_INGEST_TOKEN',
        'SENTINEL_RESPONSE_TOKEN','SENTINEL_ACCOUNT_HASH_KEY','RECIPE_SERVICE_TOKEN')
    $Vars = @{}
    foreach ($Line in [IO.File]::ReadAllLines($EnvFile)) {
        if ($Line -match '^([A-Z][A-Z0-9_]*)=(.*)$') { $Vars[$matches[1]] = $matches[2] }
    }
    foreach ($Name in $SecretNames) {
        if (!$Vars.ContainsKey($Name) -or $Vars[$Name].Length -lt 32) {
            throw "Missing/short $Name in .env. Fix locally without sharing secrets."
        }
    }
    $OnDiskRecipeToken = if (Test-Path $TokenFile) { [IO.File]::ReadAllText($TokenFile).Trim() } else { '' }
    if ($OnDiskRecipeToken -ne $Vars['RECIPE_SERVICE_TOKEN']) {
        throw 'Backend .env recipe token differs from host token file; manual reconcile required.'
    }
    Note 'BACKEND_QWEN_TOKEN_BRIDGE: CONFIGURED'

    Push-Location $Root
    try {
        docker compose -f docker-compose.yml -f team-services/docker-compose.models.override.yml config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Combined Compose config validation failed.' }
    } finally { Pop-Location }
    Note 'COMPOSE_OVERLAY: VALID'

    $SentinelVenv = Join-Path $HOME '.foodinsightai\sentinel-venv-312'
    if ($InstallSentinelDeps) {
        $SentinelPython = Join-Path $SentinelVenv 'Scripts\python.exe'
        if (!(Test-Path $SentinelPython)) {
            & py -3.12 -m venv $SentinelVenv
            if ($LASTEXITCODE -ne 0) { throw 'Sentinel Python virtual environment creation failed.' }
        }
        & $SentinelPython -m pip install -r (Join-Path $Services 'sentinel-service\backend\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Sentinel dependency installation failed.' }
        & $SentinelPython -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Sentinel Python dependency conflict.' }
        Note 'SENTINEL_DEPENDENCIES: INSTALLED'
    } else { Note 'SENTINEL_DEPENDENCIES: INSTALL WITH -InstallSentinelDeps' }

    $QwenPython = Join-Path $Services '.qwen-venv\Scripts\python.exe'
    if ($InstallQwenDeps -or $DownloadQwen) {
        if (!(Test-Path $QwenPython)) {
            & py -3.12 -m venv (Join-Path $Services '.qwen-venv')
            if ($LASTEXITCODE -ne 0) { throw 'Qwen Python virtual environment creation failed.' }
        }
    }
    if ($InstallQwenDeps) {
        # CUDA wheel availability varies by driver/platform. Failure is explicit, never silently CPU-only.
        & $QwenPython -m pip install --index-url https://download.pytorch.org/whl/cu130 'torch==2.14.1'
        if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch wheel could not be installed; see PyTorch RTX platform instructions.' }
        & $QwenPython -m pip install -r (Join-Path $Services 'qwen_service\requirements-qwen.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Qwen dependency installation failed.' }
        & $QwenPython -c 'import torch; assert torch.cuda.is_available(), "CUDA unavailable"; print("QWEN_CUDA: READY")'
        if ($LASTEXITCODE -ne 0) { throw 'Qwen GPU unavailable. Do not start inference in CPU mode.' }
        Note 'QWEN_DEPENDENCIES_AND_CUDA: INSTALLED_AND_CHECKED'
    } else { Note 'QWEN_DEPENDENCIES: INSTALL WITH -InstallQwenDeps' }
    if ($DownloadQwen) {
        if (!(Test-Path $QwenPython)) { throw 'Qwen venv missing; add -InstallQwenDeps before -DownloadQwen.' }
        Push-Location $Services
        try {
            & $QwenPython -m qwen_service.download_qwen
            if ($LASTEXITCODE -ne 0) { throw 'Pinned official Qwen3-4B download failed.' }
        } finally { Pop-Location }
        Note 'QWEN_PINNED_SNAPSHOT: DOWNLOADED (full GPU inference still requires test)'
    } else { Note 'QWEN_WEIGHTS: DOWNLOAD SEPARATELY WITH -DownloadQwen' }
    Note 'RESULT: TEAM_PREPARE_COMPLETE_NO_SERVICES_STARTED'
} catch {
    Note ('RESULT: PREPARE_FAILED ' + $_.Exception.Message)
    throw
} finally {
    New-Item -ItemType Directory -Path (Split-Path $Report -Parent) -Force | Out-Null
    $Records | Out-File -LiteralPath $Report -Encoding UTF8 -Width 260
    Write-Host "REPORT: $Report"
}
