param(
    [switch]$WithWorker
)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 can receive both `Path` and `PATH` from GUI hosts.
# Start-Process builds a case-insensitive environment dictionary and crashes on
# that duplicate, so normalize the process-local copy before launching services.
$processEnvironment = [Environment]::GetEnvironmentVariables(
    [EnvironmentVariableTarget]::Process
)
$processPath = $processEnvironment["Path"]
if ([string]::IsNullOrWhiteSpace($processPath)) {
    $processPath = $processEnvironment["PATH"]
}
[Environment]::SetEnvironmentVariable(
    "Path",
    $null,
    [EnvironmentVariableTarget]::Process
)
[Environment]::SetEnvironmentVariable(
    "PATH",
    $null,
    [EnvironmentVariableTarget]::Process
)
[Environment]::SetEnvironmentVariable(
    "Path",
    $processPath,
    [EnvironmentVariableTarget]::Process
)
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "outputs\runtime"
$frontendRoot = Join-Path $projectRoot "frontend"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$vite = Get-ChildItem `
    -Path (Join-Path $frontendRoot "node_modules\.pnpm\vite@*\node_modules\vite\bin\vite.js") |
    Select-Object -First 1

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment is missing at $python"
}
if ($null -eq $vite) {
    throw "Frontend dependencies are missing. Install them before starting."
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "configure_local_frontend.ps1")

$backend = Start-Process `
    -FilePath $python `
    -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput (Join-Path $runtimeRoot "backend.log") `
    -RedirectStandardError (Join-Path $runtimeRoot "backend.err.log") `
    -WindowStyle Hidden `
    -PassThru

$frontend = Start-Process `
    -FilePath "C:\Program Files\nodejs\node.exe" `
    -ArgumentList $vite.FullName, "dev", "--host", "127.0.0.1", "--port", "3000" `
    -WorkingDirectory $frontendRoot `
    -RedirectStandardOutput (Join-Path $runtimeRoot "frontend.log") `
    -RedirectStandardError (Join-Path $runtimeRoot "frontend.err.log") `
    -WindowStyle Hidden `
    -PassThru

[IO.File]::WriteAllText((Join-Path $runtimeRoot "backend.pid"), "$($backend.Id)")
[IO.File]::WriteAllText((Join-Path $runtimeRoot "frontend.pid"), "$($frontend.Id)")

if ($WithWorker) {
    $worker = Start-Process `
        -FilePath $python `
        -ArgumentList "scripts\run_fairhire_worker.py" `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput (Join-Path $runtimeRoot "worker.log") `
        -RedirectStandardError (Join-Path $runtimeRoot "worker.err.log") `
        -WindowStyle Hidden `
        -PassThru
    [IO.File]::WriteAllText((Join-Path $runtimeRoot "worker.pid"), "$($worker.Id)")
}

Write-Host "FairHireAI backend: http://127.0.0.1:8000/docs"
Write-Host "FairHireAI frontend: http://127.0.0.1:3000"
if ($WithWorker) {
    Write-Host "Trusted processing/deletion worker started."
}
