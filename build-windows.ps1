param(
    [ValidateSet("All", "Release", "Debug")]
    [string]$Configuration = "All",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This build script requires Windows."
}

$repoRoot = $PSScriptRoot
$python = (
    Get-Command python.exe -CommandType Application -ErrorAction Stop |
        Select-Object -First 1
).Source
$releaseDir = Join-Path $repoRoot "dist\local-release"
$debugDir = Join-Path $repoRoot "dist\local-debug"
$buildRoot = Join-Path $repoRoot "build\local-windows"
$specDir = Join-Path $buildRoot "spec"
$guiFont = Join-Path $repoRoot "assets\fonts\JetBrainsLxgwNerdMono-Regular.ttf"
$notices = Join-Path $repoRoot "THIRD_PARTY_NOTICES.md"

function Remove-RepoBuildPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullRoot = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($fullRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the repository: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

function Invoke-Python {
    & $python @args
    if ($LASTEXITCODE -ne 0) {
        throw "python exited with code ${LASTEXITCODE}: $($args -join ' ')"
    }
}

function New-ReleaseBuild {
    Remove-RepoBuildPath -Path $releaseDir
    $releaseWork = Join-Path $buildRoot "release"
    Remove-RepoBuildPath -Path $releaseWork
    New-Item -ItemType Directory -Force -Path $releaseDir, $releaseWork, $specDir |
        Out-Null

    Invoke-Python -m PyInstaller --noconfirm --clean --onefile `
        --name "font-merger-windows-x64" `
        --distpath $releaseDir --workpath (Join-Path $releaseWork "cli") `
        --specpath $specDir `
        --collect-submodules fontTools.ttLib.tables `
        --collect-submodules fontTools.encodings `
        (Join-Path $repoRoot "Font_Merger.py")

    Invoke-Python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name "font-merger-gui-windows-x64" `
        --distpath $releaseDir --workpath (Join-Path $releaseWork "gui") `
        --specpath $specDir `
        --add-data "$guiFont;assets/fonts" `
        --add-data "$notices;." `
        --collect-submodules fontTools.ttLib.tables `
        --collect-submodules fontTools.encodings `
        (Join-Path $repoRoot "Font_Merger_GUI.py")

    $packageDir = Join-Path $releaseWork "font-merger-gui-windows-x64-package"
    New-Item -ItemType Directory -Force -Path (Join-Path $packageDir "licenses") |
        Out-Null
    Copy-Item -LiteralPath (Join-Path $releaseDir "font-merger-gui-windows-x64.exe") -Destination $packageDir
    Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE"), $notices -Destination $packageDir
    Copy-Item -Path (Join-Path $repoRoot "release-licenses\*") -Destination (Join-Path $packageDir "licenses")
    Compress-Archive -Path (Join-Path $packageDir "*") `
        -DestinationPath (Join-Path $releaseDir "font-merger-gui-windows-x64.zip") `
        -Force

    & (Join-Path $releaseDir "font-merger-windows-x64.exe") --version
    if ($LASTEXITCODE -ne 0) {
        throw "Release CLI smoke test failed with exit code $LASTEXITCODE."
    }
}

function New-DebugBuild {
    Remove-RepoBuildPath -Path $debugDir
    $debugWork = Join-Path $buildRoot "debug"
    Remove-RepoBuildPath -Path $debugWork
    New-Item -ItemType Directory -Force -Path $debugDir, $debugWork, $specDir |
        Out-Null

    Invoke-Python -m PyInstaller --noconfirm --clean --onedir --windowed --debug all `
        --name "font-merger-gui-windows-x64-debug" `
        --distpath $debugDir --workpath $debugWork --specpath $specDir `
        --add-data "$guiFont;assets/fonts" `
        --add-data "$notices;." `
        --collect-submodules fontTools.ttLib.tables `
        --collect-submodules fontTools.encodings `
        (Join-Path $repoRoot "Font_Merger_GUI.py")
}

Push-Location $repoRoot
try {
    Invoke-Python (Join-Path $repoRoot "scripts\fetch_gui_font.py") --release-assets
    Invoke-Python (Join-Path $repoRoot "scripts\prepare_gui_font.py")

    if (-not (Test-Path -LiteralPath $guiFont -PathType Leaf)) {
        throw "Prepared GUI font is missing: $guiFont"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "release-licenses") -PathType Container)) {
        throw "Release licenses are missing."
    }

    if (-not $SkipTests) {
        Invoke-Python -m unittest discover -s tests -v
    }

    if ($Configuration -in @("All", "Release")) {
        New-ReleaseBuild
    }
    if ($Configuration -in @("All", "Debug")) {
        New-DebugBuild
    }
}
finally {
    Pop-Location
}

Write-Host "Windows $Configuration build completed."
if ($Configuration -in @("All", "Release")) {
    Write-Host "Release GUI: $(Join-Path $releaseDir 'font-merger-gui-windows-x64.exe')"
    Write-Host "Release CLI: $(Join-Path $releaseDir 'font-merger-windows-x64.exe')"
}
if ($Configuration -in @("All", "Debug")) {
    Write-Host "Debug GUI: $(Join-Path $debugDir 'font-merger-gui-windows-x64-debug\font-merger-gui-windows-x64-debug.exe')"
}
