#Requires -Version 7.0

param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$outputDir = Join-Path $projectRoot "src-tauri\binaries"
$temporaryRoot = Join-Path $projectRoot "build\backend-sidecar"
$distDir = Join-Path $temporaryRoot "dist"
$workDir = Join-Path $temporaryRoot "work"
$specDir = Join-Path $temporaryRoot "spec"
$entryPoint = Join-Path $backendDir "main.py"
$scriptsDir = Join-Path $backendDir "scripts"
$targetExecutable = Join-Path $outputDir "wmt-backend-$TargetTriple.exe"

if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) {
    throw "Backend entry point not found: $entryPoint"
}

if (-not $SkipDependencyInstall) {
    & python -m pip install -r (Join-Path $backendDir "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install backend sidecar build dependencies."
    }
}

New-Item -ItemType Directory -Force -Path $outputDir, $distDir, $workDir, $specDir | Out-Null

$pyInstallerArguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "wmt-backend",
    "--distpath", $distDir,
    "--workpath", $workDir,
    "--specpath", $specDir,
    "--collect-all", "uvicorn"
)
if (Test-Path -LiteralPath $scriptsDir -PathType Container) {
    $pyInstallerArguments += @("--add-data", "$scriptsDir;scripts")
}
$pyInstallerArguments += $entryPoint

& python @pyInstallerArguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build the WMT backend sidecar."
}

$builtExecutable = Join-Path $distDir "wmt-backend.exe"
if (-not (Test-Path -LiteralPath $builtExecutable -PathType Leaf)) {
    throw "PyInstaller did not produce: $builtExecutable"
}

Copy-Item -LiteralPath $builtExecutable -Destination $targetExecutable -Force
Write-Host "[OK] Sidecar created: $targetExecutable" -ForegroundColor Green
