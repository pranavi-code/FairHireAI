$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$plainKey = [Environment]::GetEnvironmentVariable(
    "ROLEREADY_GEMINI_API_KEY",
    "User"
)
$pointer = [IntPtr]::Zero

if ([string]::IsNullOrWhiteSpace($plainKey)) {
    $secureKey = Read-Host "Paste the NEW replacement Gemini API key" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
}

try {
    if ([string]::IsNullOrWhiteSpace($plainKey) -or $plainKey.Length -lt 20) {
        throw "The Gemini API key does not look valid."
    }
    $lines = [Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            $lines.Add($line)
        }
    }
    $replacement = "ROLEREADY_GEMINI_API_KEY=$plainKey"
    $existingIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^ROLEREADY_GEMINI_API_KEY=") {
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
        $envPath,
        $lines,
        [Text.UTF8Encoding]::new($false)
    )
    $stored = Get-Content -LiteralPath $envPath |
        Where-Object { $_ -match "^ROLEREADY_GEMINI_API_KEY=.{20,}$" } |
        Select-Object -First 1
    if ($null -eq $stored) {
        throw "The Gemini key could not be verified in the local .env file."
    }
}
finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $plainKey = $null
    $secureKey = $null
}

Write-Host "Gemini key stored in FairHireAI's local git-ignored .env file."
Write-Host "The key was not printed and is not exposed to the Vite frontend."
