$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendEnv = Join-Path $projectRoot "frontend\.env"
$replacement = "VITE_API_BASE_URL=http://127.0.0.1:8000"
$lines = [Collections.Generic.List[string]]::new()

if (Test-Path -LiteralPath $frontendEnv) {
    foreach ($line in Get-Content -LiteralPath $frontendEnv) {
        $lines.Add($line)
    }
}

$existingIndex = -1
for ($index = 0; $index -lt $lines.Count; $index++) {
    if ($lines[$index] -match "^VITE_API_BASE_URL=") {
        $existingIndex = $index
        break
    }
}
if ($existingIndex -ge 0) {
    $lines[$existingIndex] = $replacement
}
else {
    $lines.Add($replacement)
}

[IO.File]::WriteAllLines(
    $frontendEnv,
    $lines,
    [Text.UTF8Encoding]::new($false)
)
Write-Host "Frontend configured to use the local FairHireAI API at port 8000."
