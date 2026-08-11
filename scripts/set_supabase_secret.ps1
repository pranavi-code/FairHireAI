param(
    [switch]$FromClipboard
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$plainKey = if ($FromClipboard) {
    (Get-Clipboard -Raw).Trim()
}
else {
    [Environment]::GetEnvironmentVariable(
        "ROLEREADY_SUPABASE_SECRET_KEY",
        "User"
    )
}
$pointer = [IntPtr]::Zero

if ([string]::IsNullOrWhiteSpace($plainKey)) {
    $secureKey = Read-Host "Paste the Supabase server secret/service-role key" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
}

try {
    $isModernSecret = $plainKey -match '^sb_secret_[A-Za-z0-9_-]{20,}$'
    $isLegacyServiceRole = $plainKey -match '^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$'
    if (-not ($isModernSecret -or $isLegacyServiceRole)) {
        throw "The Supabase server key does not look valid."
    }
    $lines = [Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            $lines.Add($line)
        }
    }
    $replacement = "ROLEREADY_SUPABASE_SECRET_KEY=$plainKey"
    $existingIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^ROLEREADY_SUPABASE_SECRET_KEY=") {
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
        Where-Object {
            $_ -match "^ROLEREADY_SUPABASE_SECRET_KEY=(sb_secret_[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$"
        } |
        Select-Object -First 1
    if ($null -eq $stored) {
        throw "The Supabase server key could not be verified in the local .env file."
    }
}
finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $plainKey = $null
    $secureKey = $null
}

Write-Host "Supabase server key stored in FairHireAI's local git-ignored .env file."
Write-Host "The key was not printed and is never exposed to the Vite frontend."
