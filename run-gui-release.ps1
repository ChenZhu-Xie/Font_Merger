param(
    [switch]$Build,
    [switch]$Wait,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$buildScript = Join-Path $repoRoot "build-windows.ps1"
$exePath = Join-Path $repoRoot "dist\local-release\font-merger-gui-windows-x64.exe"

if ($Build -or -not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    & $buildScript -Configuration Release
    if ($LASTEXITCODE -ne 0) {
        throw "Release build failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Release executable not found: $exePath"
}

$start = @{
    FilePath = $exePath
    WorkingDirectory = Split-Path -Parent $exePath
    PassThru = $true
}
if ($AppArgs.Count -gt 0) {
    $start.ArgumentList = $AppArgs
}
$process = Start-Process @start
if ($Wait) {
    $process.WaitForExit()
    exit $process.ExitCode
}
