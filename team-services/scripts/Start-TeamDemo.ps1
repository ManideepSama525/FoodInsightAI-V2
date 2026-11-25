<#
EXPERIMENTAL startup for a CLEAN teammate laptop, not the author's live machine.
Requires Prepare-TeamDemo.ps1 successfully completed and compatible GPU dependencies.
Starts separate localhost-only Qwen and Sentinel host processes and then Docker Compose.
Never call this on a computer already running FoodInsightAI without resolving ports first.
#>
[CmdletBinding()]
param([switch]$ConfirmCleanLaptop)
$ErrorActionPreference = 'Stop'
if (!$ConfirmCleanLaptop) { throw 'Refusing startup without -ConfirmCleanLaptop.' }
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Services = Join-Path $Root 'team-services'
$EnvFile = Join-Path $Root '.env'
$SentinelPython = Join-Path $HOME '.foodinsightai\sentinel-venv-312\Scripts\python.exe'
$QwenPython = Join-Path $Services '.qwen-venv\Scripts\python.exe'
$LogDir = Join-Path $HOME '.foodinsightai\team-demo-logs'
$TestScript = Join-Path $Services 'scripts\Check-TeamDemo.ps1'
function Require-File([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file absent: $Path" }
}
function Port-IsOpen([int]$Port) {
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Async = $Client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (!$Async.AsyncWaitHandle.WaitOne(350)) { return $false }
        try { $Client.EndConnect($Async); return $true } catch { return $false }
    } finally { $Client.Close() }
}
Require-File $EnvFile
Require-File $SentinelPython
Require-File $QwenPython
Require-File (Join-Path $Services 'sentinel-service\backend\safe_demo_app.py')
Require-File (Join-Path $Services 'sentinel-service\backend\run_local.py')
Require-File (Join-Path $Services 'qwen_service\run_service.py')
Require-File (Join-Path $Services 'docker-compose.models.override.yml')
Require-File (Join-Path $Root 'docker-compose.yml')
foreach ($Port in @(3000,8000,8010,8023,7474,7687)) {
    if (Port-IsOpen $Port) { throw "Port $Port already in use. Stop here; live deployment may be running." }
}
$Vars = @{}
foreach ($Line in [IO.File]::ReadAllLines($EnvFile)) {
    if ($Line -match '^([A-Z][A-Z0-9_]*)=(.*)$') { $Vars[$matches[1]] = $matches[2] }
}
foreach ($Name in @('SENTINEL_INGEST_TOKEN','SENTINEL_RESPONSE_TOKEN',
                   'SENTINEL_ACCOUNT_HASH_KEY','SENTINEL_ANALYST_ACTION_TOKEN',
                   'JWT_SECRET_KEY','NEO4J_PASSWORD','RECIPE_SERVICE_TOKEN')) {
    if (!$Vars.ContainsKey($Name) -or $Vars[$Name].Length -lt 32) {
        throw "Missing/short $Name in .env; run Prepare-TeamDemo first."
    }
}
$TokenFile = Join-Path $HOME '.foodinsightai\recipe_service_token.txt'
Require-File $TokenFile
if ([IO.File]::ReadAllText($TokenFile).Trim() -ne $Vars['RECIPE_SERVICE_TOKEN']) {
    throw 'Backend and Qwen tokens differ; fix before starting services.'
}
$ModelDir = Join-Path $Root 'model_cache\Qwen3-4B'
if (!(Test-Path (Join-Path $ModelDir 'config.json'))) { throw 'Pinned Qwen3-4B snapshot not present.' }
$QwenShards = @(Get-ChildItem -LiteralPath $ModelDir -File -Filter 'model-*-of-*.safetensors')
if ($QwenShards.Count -ne 3) { throw 'Expected 3 Qwen model shards.' }
& $QwenPython (Join-Path $Services 'qwen_service\run_service.py') --check
if ($LASTEXITCODE -ne 0) { throw 'Qwen CUDA and model preflight failed.' }

foreach ($Name in @('SENTINEL_INGEST_TOKEN','SENTINEL_RESPONSE_TOKEN',
                   'SENTINEL_ACCOUNT_HASH_KEY','SENTINEL_ANALYST_ACTION_TOKEN')) {
    [Environment]::SetEnvironmentVariable($Name, $Vars[$Name], 'Process')
}
[Environment]::SetEnvironmentVariable('FOODINSIGHTAI_INTERNAL_URL', 'http://127.0.0.1:8000', 'Process')
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$SentinelLog = Join-Path $LogDir 'sentinel.stdout.log'
$SentinelErr = Join-Path $LogDir 'sentinel.stderr.log'
$QwenLog = Join-Path $LogDir 'qwen.stdout.log'
$QwenErr = Join-Path $LogDir 'qwen.stderr.log'
foreach ($LogFile in @($SentinelLog,$SentinelErr,$QwenLog,$QwenErr)) {
    if (Test-Path $LogFile) { throw "Existing log file; refusing silent overwrite: $LogFile" }
}
$Sentinel = Start-Process -FilePath $SentinelPython -PassThru -WindowStyle Hidden `
    -ArgumentList @((Join-Path $Services 'sentinel-service\backend\run_local.py')) `
    -RedirectStandardOutput $SentinelLog -RedirectStandardError $SentinelErr
Write-Host "SENTINEL_STARTED_PID: $($Sentinel.Id) (localhost-only, log in user profile)"
$Qwen = Start-Process -FilePath $QwenPython -PassThru -WindowStyle Hidden `
    -ArgumentList @((Join-Path $Services 'qwen_service\run_service.py'), '--serve') `
    -RedirectStandardOutput $QwenLog -RedirectStandardError $QwenErr
Write-Host "QWEN_STARTED_PID: $($Qwen.Id) (localhost-only, 4-bit GPU, lazy load)"
try {
    Push-Location $Root
    try {
        docker compose -p foodinsight-teamdemo -f docker-compose.yml `
            -f team-services/docker-compose.models.override.yml up -d --build
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose up failed.' }
    } finally { Pop-Location }
} catch {
    Write-Warning 'Compose failed. Host service processes may still be running; inspect local logs.'
    throw
}
Write-Host 'TEAM_COMPOSE_STARTED: Services requested; runtime/data health not guaranteed.'
Write-Host 'QWEN_HEALTH: A 200 response does NOT mean recipe inference has been tested.'
& $TestScript
Write-Host 'FOLLOWUP_REQUIRED: actual authenticated recipe, food scans, Sentinel ingestion, data and regulatory workflows.'
