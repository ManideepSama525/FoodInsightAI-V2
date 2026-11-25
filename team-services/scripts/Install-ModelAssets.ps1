<#
Install the 11 SHA-256 verified private release assets into a fresh clone.
Never overwrites a preexisting model whose SHA-256 differs.
Prerequisites: GitHub CLI with access to the private model repo, PowerShell 5.1+.
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
)
$ErrorActionPreference = "Stop"
$ReleaseRepo = "ManideepSama525/FoodInsightAI-V2-Model-Assets"
$ReleaseTag = "team-demo-models-v1"
$ArchiveName = "FoodInsightAI-Team-Models-v1.zip"
$ExpectedHash = "BD025F074C9F4DE1BF32AE1EDBC52301D7B22848CE72D720093DA8AA1455FB68"
$Gh = (Get-Command gh.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
if (!$Gh) {
    $PortableGh = Join-Path $HOME "Tools\GitHubCLI\bin\gh.exe"
    if (Test-Path -LiteralPath $PortableGh) { $Gh = $PortableGh }
}
if (!$Gh) { throw "GitHub CLI not found. Install GitHub CLI and authenticate to the private model repo." }
if (!(Test-Path -LiteralPath $ProjectRoot -PathType Container)) { throw "Project root missing: $ProjectRoot" }
$Cache = Join-Path $env:TEMP "foodinsight-verified-models-v1"
New-Item -ItemType Directory -Path $Cache -Force | Out-Null
$Archive = Join-Path $Cache $ArchiveName
if (!(Test-Path -LiteralPath $Archive -PathType Leaf)) {
    Write-Host "Downloading authenticated private release..."
    & $Gh release download $ReleaseTag --repo $ReleaseRepo --pattern $ArchiveName --dir $Cache
    if ($LASTEXITCODE -ne 0) { throw "Release download failed. Check GitHub access." }
}
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
if ($Hash -ne $ExpectedHash) { throw "Private release archive SHA-256 does not match." }
Write-Host "RELEASE_ARCHIVE_SHA256: VERIFIED"
$Staging = Join-Path $env:TEMP ("foodinsight-asset-stage-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Staging -Force | Out-Null
try {
    Expand-Archive -LiteralPath $Archive -DestinationPath $Staging
    $Csv = Join-Path $Staging "model_checksums.csv"
    if (!(Test-Path -LiteralPath $Csv)) { throw "Model checksums CSV absent from release archive" }
    $Entries = @(Import-Csv -LiteralPath $Csv)
    if ($Entries.Count -ne 11) { throw "Expected exactly 11 files, found $($Entries.Count)" }
    $Copies = @()
    foreach ($Entry in $Entries) {
        $Relative = [string]$Entry.RelativePath
        if ($Relative -match '(^[\/])|(^[a-zA-Z]:)|(^|[\/])\.\.([\/]|$)') { throw "Unsafe path in manifest" }
        $Relative = $Relative.Replace('/', '\')
        $Source = Join-Path $Staging $Relative
        if (!(Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Model missing: $Relative" }
        $SourceInfo = Get-Item -LiteralPath $Source
        if ($SourceInfo.Length -ne [long]$Entry.SizeBytes) { throw "File size mismatch: $Relative" }
        $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
        if ($SourceHash -ne $Entry.SHA256) { throw "Asset SHA-256 mismatch: $Relative" }
        $Dest = Join-Path $ProjectRoot $Relative
        if (Test-Path -LiteralPath $Dest) {
            $DestHash = (Get-FileHash -LiteralPath $Dest -Algorithm SHA256).Hash
            if ($DestHash -ne $Entry.SHA256) { throw "Existing file differs; will not overwrite: $Relative" }
        } else {
            $Copies += [pscustomobject]@{ Source = $Source; Destination = $Dest }
        }
    }
    foreach ($Copy in $Copies) {
        New-Item -ItemType Directory -Path (Split-Path $Copy.Destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $Copy.Source -Destination $Copy.Destination
    }
    Write-Host "MODEL_ASSETS_VERIFIED: 11/11"
    Write-Host "NEW_FILES_INSTALLED: $($Copies.Count)"
    Write-Host "NO_EXISTING_MODEL_OVERWRITTEN"
} finally {
    Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
}
