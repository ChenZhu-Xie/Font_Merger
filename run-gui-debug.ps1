param(
    [switch]$Build,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = "Stop"

function Hide-DedicatedConsoleWindow {
    if ($env:OS -ne "Windows_NT") {
        return
    }

    if (-not ("FontMerger.ConsoleWindow" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace FontMerger {
    public static class ConsoleWindow {
        [DllImport("kernel32.dll")]
        public static extern IntPtr GetConsoleWindow();

        [DllImport("kernel32.dll")]
        public static extern uint GetConsoleProcessList(uint[] processList, uint processCount);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool ShowWindow(IntPtr windowHandle, int command);
    }
}
"@
    }

    $consoleProcesses = [uint[]]::new(2)
    if ([FontMerger.ConsoleWindow]::GetConsoleProcessList($consoleProcesses, 2) -eq 1) {
        $consoleWindow = [FontMerger.ConsoleWindow]::GetConsoleWindow()
        if ($consoleWindow -ne [IntPtr]::Zero) {
            [void][FontMerger.ConsoleWindow]::ShowWindow($consoleWindow, 0)
        }
    }
}

Hide-DedicatedConsoleWindow

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
