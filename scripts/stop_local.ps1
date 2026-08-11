$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "outputs\runtime"
foreach ($name in @("backend", "frontend", "worker")) {
    $pidPath = Join-Path $runtimeRoot "$name.pid"
    if (-not (Test-Path -LiteralPath $pidPath)) {
        continue
    }
    $processId = [int](Get-Content -LiteralPath $pidPath -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        Stop-Process -Id $processId
        Write-Host "Stopped $name process $processId."
    }
    Remove-Item -LiteralPath $pidPath
}
