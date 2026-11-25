<# Read-only HTTP checks; no secrets printed and no model inference requested. #>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Results = New-Object 'System.Collections.Generic.List[string]'
$Checks = @(
    @{ Name = 'frontend'; Url = 'http://127.0.0.1:3000/' },
    @{ Name = 'backend'; Url = 'http://127.0.0.1:8000/api/v1/system/readiness' },
    @{ Name = 'qwen'; Url = 'http://127.0.0.1:8023/healthz' },
    @{ Name = 'sentinel'; Url = 'http://127.0.0.1:8010/health' }
)
foreach ($Check in $Checks) {
    try {
        $Response = Invoke-WebRequest -Uri $Check.Url -UseBasicParsing -TimeoutSec 10
        $Message = '{0}: HTTP_{1}' -f $Check.Name, [int]$Response.StatusCode
    } catch {
        $Message = '{0}: UNREACHABLE' -f $Check.Name
    }
    $Results.Add($Message)
    Write-Host $Message
}
Write-Host 'CHECK_ONLY: No app data or secrets modified.'
