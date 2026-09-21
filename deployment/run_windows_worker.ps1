param(
    [string]$ProjectRoot = "D:\FairHireAI",
    [double]$PollSeconds = 5
)

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python = Join-Path $resolvedRoot ".venv\Scripts\python.exe"
$preflight = Join-Path $resolvedRoot "scripts\preflight_deployment.py"
$worker = Join-Path $resolvedRoot "scripts\run_fairhire_worker.py"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "FairHireAI Python environment is missing: $python"
}

Set-Location -LiteralPath $resolvedRoot
& $python $preflight worker
if ($LASTEXITCODE -ne 0) {
    throw "Worker deployment preflight failed"
}

& $python $worker --poll-seconds $PollSeconds
exit $LASTEXITCODE
