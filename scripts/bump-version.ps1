#Requires -Version 7.0
<#
.SYNOPSIS
Bumpa versão do WMT Desktop e prepara para build

.PARAMETER NewVersion
Versão nova (ex: "1.0.1")

.PARAMETER Type
"major", "minor" ou "patch" para auto-increment

.EXAMPLE
.\bump-version.ps1 -NewVersion "1.0.1"
.\bump-version.ps1 -Type "minor"  # 1.0.0 → 1.1.0
#>

param(
    [string]$NewVersion,
    [ValidateSet("major", "minor", "patch")]
    [string]$Type
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host "`n========== $Message ==========" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

$tauriConfPath = ".\src-tauri\tauri.conf.json"
$packagePath = ".\package.json"

if (-not (Test-Path $tauriConfPath)) {
    Write-Host "✗ Não encontrado: $tauriConfPath" -ForegroundColor Red
    exit 1
}

Write-Header "Bumpar Versão WMT"

# Ler versão atual
$tauriConf = Get-Content $tauriConfPath -Raw | ConvertFrom-Json
$currentVersion = $tauriConf.version
Write-Host "Versão atual: $currentVersion"

# Determinar nova versão
if ($Type) {
    $parts = $currentVersion -split '\.'
    [int]$major = $parts[0]
    [int]$minor = $parts[1]
    [int]$patch = $parts[2]

    switch ($Type) {
        "major" { $major++; $minor = 0; $patch = 0 }
        "minor" { $minor++; $patch = 0 }
        "patch" { $patch++ }
    }

    $NewVersion = "$major.$minor.$patch"
}

Write-Host "Nova versão: $NewVersion"

# Atualizar tauri.conf.json
$tauriConf.version = $NewVersion
$tauriConf | ConvertTo-Json -Depth 10 | Out-File $tauriConfPath -Encoding UTF8
Write-Success "Atualizado: $tauriConfPath"

# Atualizar package.json
$package = Get-Content $packagePath -Raw | ConvertFrom-Json
$package.version = $NewVersion
$package | ConvertTo-Json -Depth 10 | Out-File $packagePath -Encoding UTF8
Write-Success "Atualizado: $packagePath"

Write-Header "Próximos Passos"
Write-Host @"
1. Fazer commit:
   git add src-tauri/tauri.conf.json package.json
   git commit -m "Bump version to $NewVersion"

2. Fazer build:
   pnpm build:tauri

3. Fazer tag e push:
   git tag v$NewVersion
   git push origin v$NewVersion

4. Upload dos arquivos para release:
   - src-tauri/target/release/WMT_${NewVersion}_x64_en-US.msi
   - src-tauri/target/release/WMT_${NewVersion}_x64_en-US.msi.sig

"@
