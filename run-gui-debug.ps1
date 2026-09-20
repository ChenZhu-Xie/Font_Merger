param(
    [switch]$Build,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$buildScript = Join-Path $repoRoot "build-windows.ps1"
$exePath = Join-Path $repoRoot "dist\local-debug\font-merger-gui-windows-x64-debug\font-merger-gui-windows-x64-debug.exe"

if ($Build -or -not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    & $buildScript -Configuration Debug
    if ($LASTEXITCODE -ne 0) {
        throw "Debug build failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Debug executable not found: $exePath"
}

Push-Location (Split-Path -Parent $exePath)
try {
    & $exePath @AppArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
