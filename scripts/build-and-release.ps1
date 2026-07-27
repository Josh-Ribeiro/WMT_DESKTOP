#Requires -Version 7.0
<#
.SYNOPSIS
Script completo: Build + Version + Release para WMT Desktop

.PARAMETER Type
"major", "minor", "patch" ou vazio para nÃ£o mudar versÃ£o

.PARAMETER SkipTest
Se true, pula testes locais

.PARAMETER BackendUrl
URL do backend usada pelo app empacotado. Ex: http://10.10.10.20:8000

.PARAMETER UpdateEndpoint
Endpoint do updater. Se omitido, usa BackendUrl + /api/updates/latest.json

.PARAMETER Channel
Canal de release: prod usa latest.json; debug usa latest-debug.json e instala lado a lado

.PARAMETER ReleaseNotes
Mensagem exibida ao usuario quando a atualizacao estiver disponivel

.PARAMETER ReleaseNotesFile
Caminho de um arquivo TXT ou Markdown com as notas da atualizacao

.PARAMETER SkipReleaseNotesPrompt
Nao solicita notas interativamente; usa a mensagem padrao quando nenhuma nota for informada

.EXAMPLE
.\build-and-release.ps1 -Type "patch"
.\build-and-release.ps1 -Type "minor"
#>

param(
    [ValidateSet("major", "minor", "patch", "")]
    [string]$Type = "",
    [string]$BackendUrl = "",
    [string]$UpdateEndpoint = "",
    [ValidateSet("prod", "debug")]
    [string]$Channel = "prod",
    [string]$ReleaseNotes = "",
    [string]$ReleaseNotesFile = "",
    [switch]$SkipReleaseNotesPrompt,
    [switch]$SkipTest,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

if ($Help) {
    $helpMessage = @(
        "DESCRICAO:",
        "  Script automatizado para versionar, buildar e preparar release do WMT Desktop",
        "",
        "USO:",
        "  .\build-and-release.ps1 -Type patch",
        "  .\build-and-release.ps1 -Type minor -SkipTest",
        "  .\build-and-release.ps1 -BackendUrl http://10.10.10.20:8000",
        "  .\build-and-release.ps1 -BackendUrl http://10.10.10.20:8000 -UpdateEndpoint http://10.10.10.20:8000/api/updates/latest.json",
        "  .\build-and-release.ps1 -Channel debug -BackendUrl http://10.10.10.20:8000",
        "",
        "OPCOES:",
        "  -Type [major|minor|patch]  Tipo de versionamento (opcional)",
        "  -BackendUrl                URL do backend para o app empacotado",
        "  -UpdateEndpoint            URL do latest.json para auto-update",
        "  -Channel [prod|debug]      Canal do update; debug instala separado e usa latest-debug.json",
        "  -ReleaseNotes              Texto exibido no aviso de atualizacao",
        "  -ReleaseNotesFile          Arquivo TXT/Markdown com as notas da atualizacao",
        "  -SkipReleaseNotesPrompt    Nao pergunta as notas durante o build",
        "  -SkipTest                  Pula testes locais do MSI",
        "  -Help                      Mostra esta ajuda",
        "",
        "EXEMPLOS:",
        "  .\build-and-release.ps1 -Type patch",
        "  .\build-and-release.ps1 -Type minor",
        "  .\build-and-release.ps1",
        "  .\build-and-release.ps1 -Type patch -ReleaseNotes ""Busca universal mais rapida e correcoes no monitor.""",
        "  .\build-and-release.ps1 -Type patch -ReleaseNotesFile .\notas.md",
        "  .\build-and-release.ps1 -BackendUrl http://10.10.10.20:8000",
        "  .\build-and-release.ps1 -BackendUrl http://10.10.10.20:8000 -UpdateEndpoint http://10.10.10.20:8000/api/updates/latest.json",
        "  .\build-and-release.ps1 -Channel debug -BackendUrl http://10.10.10.20:8000"
    ) -join [Environment]::NewLine
    Write-Host $helpMessage
    exit 0
}
Write-Header "WMT Desktop Build & Release"

$EffectiveBackendUrl = ""
if ($BackendUrl) {
    $EffectiveBackendUrl = $BackendUrl.TrimEnd("/")
    $env:VITE_API_BASE_URL = $EffectiveBackendUrl
}
elseif ($env:VITE_API_BASE_URL) {
    $EffectiveBackendUrl = $env:VITE_API_BASE_URL.TrimEnd("/")
    $env:VITE_API_BASE_URL = $EffectiveBackendUrl
}

$EffectiveUpdateEndpoint = ""
if ($UpdateEndpoint) {
    $EffectiveUpdateEndpoint = $UpdateEndpoint.TrimEnd("/")
}
elseif ($EffectiveBackendUrl) {
    $latestFileName = if ($Channel -eq "debug") { "latest-debug.json" } else { "latest.json" }
    $EffectiveUpdateEndpoint = "$EffectiveBackendUrl/api/updates/$latestFileName"
}

$updaterPrivateKeyPath = Resolve-Path ".\secrets\wmt-updater.key" -ErrorAction SilentlyContinue
if ($updaterPrivateKeyPath) {
    $env:TAURI_SIGNING_PRIVATE_KEY = $updaterPrivateKeyPath.Path
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
    Write-Info "Chave privada do updater configurada: $($updaterPrivateKeyPath.Path)"
}
else {
    Write-Warning-Custom "Chave do updater nÃ£o encontrada em .\secrets\wmt-updater.key"
}

# ============================================================================
# PASSO 1: Preparar ambiente
# ============================================================================

Write-Header "1. Verificando Ambiente"

$tauriConfPath = ".\src-tauri\tauri.conf.json"
$packagePath = ".\package.json"
$tauriConfOriginal = if (Test-Path $tauriConfPath) { Get-Content $tauriConfPath -Raw } else { "" }
$tauriConfProdSnapshot = if ($tauriConfOriginal) { $tauriConfOriginal | ConvertFrom-Json } else { $null }
$script:DebugTauriConfigApplied = $false

function Restore-ProductionTauriConfig {
    if (-not $script:DebugTauriConfigApplied -or -not $tauriConfProdSnapshot) {
        return
    }

    $tauriConf = Get-Content $tauriConfPath -Raw | ConvertFrom-Json
    $tauriConf.productName = $tauriConfProdSnapshot.productName
    $tauriConf.identifier = $tauriConfProdSnapshot.identifier
    if ($tauriConf.app.windows -and $tauriConf.app.windows.Count -gt 0 -and $tauriConfProdSnapshot.app.windows -and $tauriConfProdSnapshot.app.windows.Count -gt 0) {
        $tauriConf.app.windows[0].title = $tauriConfProdSnapshot.app.windows[0].title
    }
    if ($tauriConfProdSnapshot.plugins.updater.endpoints) {
        $tauriConf.plugins.updater.endpoints = $tauriConfProdSnapshot.plugins.updater.endpoints
    }
    $tauriConf.plugins.updater.dangerousInsecureTransportProtocol = $tauriConfProdSnapshot.plugins.updater.dangerousInsecureTransportProtocol
    $tauriConf.bundle.createUpdaterArtifacts = $tauriConfProdSnapshot.bundle.createUpdaterArtifacts
    $tauriConf | ConvertTo-Json -Depth 20 | Out-File $tauriConfPath -Encoding UTF8
    $script:DebugTauriConfigApplied = $false
    Write-Success "Config Tauri de producao restaurada apos build debug."
}

trap {
    Restore-ProductionTauriConfig
    throw $_
}

if (-not (Test-Path $tauriConfPath)) {
    Write-Host "âœ— Arquivo nÃ£o encontrado: $tauriConfPath" -ForegroundColor Red
    exit 1
}

# Ler versÃ£o atual
$tauriConf = Get-Content $tauriConfPath -Raw | ConvertFrom-Json
$currentVersion = $tauriConf.version
Write-Success "VersÃ£o atual: $currentVersion"

# Verificar dependÃªncias
$checks = @{
    "Node.js" = { node --version }
    "Python" = { python --version }
    "pnpm" = { pnpm --version }
    "Cargo (Rust)" = { cargo --version }
}

foreach ($check in $checks.GetEnumerator()) {
    try {
        $result = & $check.Value 2>&1
        Write-Success "$($check.Key): $result"
    }
    catch {
        Write-Warning-Custom "$($check.Key): NÃƒO ENCONTRADO"
    }
}

# ============================================================================
# PASSO 2: Bumpar versÃ£o (se solicitado)
# ============================================================================

if ($Type) {
    Write-Header "2. Bumpar VersÃ£o"

    $parts = $currentVersion -split '\.'
    [int]$major = $parts[0]
    [int]$minor = $parts[1]
    [int]$patch = $parts[2]

    switch ($Type) {
        "major" { $major++; $minor = 0; $patch = 0 }
        "minor" { $minor++; $patch = 0 }
        "patch" { $patch++ }
    }

    $newVersion = "$major.$minor.$patch"
    Write-Info "Atualizando versÃ£o: $currentVersion â†’ $newVersion"

    $tauriConf.version = $newVersion
    $tauriConf | ConvertTo-Json -Depth 10 | Out-File $tauriConfPath -Encoding UTF8

    $package = Get-Content $packagePath -Raw | ConvertFrom-Json
    $package.version = $newVersion
    $package | ConvertTo-Json -Depth 10 | Out-File $packagePath -Encoding UTF8

    $currentVersion = $newVersion
    Write-Success "VersÃ£o bumped para $newVersion"
}
else {
    Write-Info "VersÃ£o: $currentVersion (nÃ£o serÃ¡ alterada)"
}

$defaultReleaseNotes = if ($Channel -eq "debug") {
    "WMT Desktop Debug $currentVersion"
}
else {
    "WMT Desktop $currentVersion"
}

if ($ReleaseNotes -and $ReleaseNotesFile) {
    throw "Use apenas -ReleaseNotes ou -ReleaseNotesFile, nao os dois ao mesmo tempo."
}

$effectiveReleaseNotes = ""
if ($ReleaseNotesFile) {
    $resolvedReleaseNotesFile = Resolve-Path $ReleaseNotesFile -ErrorAction Stop
    $effectiveReleaseNotes = (Get-Content $resolvedReleaseNotesFile.Path -Raw).Trim()
    Write-Success "Notas carregadas de: $($resolvedReleaseNotesFile.Path)"
}
elseif ($ReleaseNotes) {
    $effectiveReleaseNotes = $ReleaseNotes.Trim()
}
elseif ($env:WMT_RELEASE_NOTES) {
    $effectiveReleaseNotes = $env:WMT_RELEASE_NOTES.Trim()
    Write-Info "Notas carregadas da variavel WMT_RELEASE_NOTES."
}
elseif (-not $SkipReleaseNotesPrompt) {
    Write-Header "Notas da atualizacao"
    Write-Info "Digite a mensagem que sera exibida no atualizador."
    Write-Info "Use uma linha por item e pressione Enter em uma linha vazia para concluir."

    $releaseNoteLines = [System.Collections.Generic.List[string]]::new()
    while ($true) {
        $releaseNoteLine = Read-Host "Nota"
        if ([string]::IsNullOrWhiteSpace($releaseNoteLine)) {
            break
        }
        $releaseNoteLines.Add($releaseNoteLine.Trim())
    }
    $effectiveReleaseNotes = ($releaseNoteLines -join [Environment]::NewLine).Trim()
}

if ([string]::IsNullOrWhiteSpace($effectiveReleaseNotes)) {
    $effectiveReleaseNotes = $defaultReleaseNotes
    Write-Info "Nenhuma nota informada; sera usada a mensagem padrao."
}
else {
    Write-Success "Notas da atualizacao registradas."
}

if ($Channel -eq "debug" -or $EffectiveUpdateEndpoint) {
    $tauriConf = Get-Content $tauriConfPath -Raw | ConvertFrom-Json
    if ($Channel -eq "debug") {
        $tauriConf.productName = "WMT Desktop Debug"
        $tauriConf.identifier = "com.wmt.desktop.debug"
        if ($tauriConf.app.windows -and $tauriConf.app.windows.Count -gt 0) {
            $tauriConf.app.windows[0].title = "WMT Desktop Debug"
        }
    }
    else {
        $tauriConf.productName = "WMT Desktop"
        $tauriConf.identifier = "com.wmt.desktop"
        if ($tauriConf.app.windows -and $tauriConf.app.windows.Count -gt 0) {
            $tauriConf.app.windows[0].title = "WMT Desktop"
        }
    }
    if ($EffectiveUpdateEndpoint) {
        $tauriConf.plugins.updater.endpoints = @($EffectiveUpdateEndpoint)
        $tauriConf.plugins.updater.dangerousInsecureTransportProtocol = $true
        $tauriConf.bundle.createUpdaterArtifacts = $true
    }
    $tauriConf | ConvertTo-Json -Depth 20 | Out-File $tauriConfPath -Encoding UTF8
    if ($Channel -eq "debug") {
        $script:DebugTauriConfigApplied = $true
    }
    if ($EffectiveUpdateEndpoint) {
        Write-Success "Updater configurado para canal '$Channel': $EffectiveUpdateEndpoint"
    }
    elseif ($Channel -eq "debug") {
        Write-Success "Identidade debug configurada para instalacao lado a lado."
    }
}

# ============================================================================
# PASSO 3: Instalar dependÃªncias
# ============================================================================

Write-Header "3. Instalando DependÃªncias"

Write-Info "Executando: pnpm install"
& pnpm install
Write-Success "DependÃªncias instaladas"

# ============================================================================
# PASSO 4: Build Frontend
# ============================================================================

Write-Header "4. Build do Frontend"

Write-Info "Compilando React + TypeScript + Tailwind..."
if ($EffectiveBackendUrl) {
    Write-Info "Backend configurado no app: $EffectiveBackendUrl"
}
else {
    Write-Warning-Custom "Backend do app ficarÃ¡ no padrÃ£o: http://127.0.0.1:8000"
}
& pnpm build
if ($LASTEXITCODE -ne 0) {
    Write-Host "âœ— Build frontend falhou!" -ForegroundColor Red
    exit 1
}
if ($EffectiveBackendUrl) {
    $compiledAssets = Get-ChildItem -Path "dist\public\assets" -Filter "*.js" -Recurse -ErrorAction SilentlyContinue
    $compiledBackendUrl = $compiledAssets | Select-String -Pattern ([regex]::Escape($EffectiveBackendUrl)) -Quiet
    if (-not $compiledBackendUrl) {
        Write-Host "âœ— A URL do backend nÃ£o foi embutida no frontend compilado: $EffectiveBackendUrl" -ForegroundColor Red
        exit 1
    }
}
Write-Success "Frontend compilado"

# ============================================================================
# PASSO 5: Build Tauri (Main Build)
# ============================================================================

Write-Header "5. Build do Tauri (MAIN - vai levar um tempo)"

Write-Info "Compilando Rust + empacotando MSI..."
Write-Info "Tempo estimado: 5-10 minutos (primeira vez: 30-45 min)"

$buildStartTime = Get-Date
& pnpm build:tauri
$buildEndTime = Get-Date
$buildDuration = $buildEndTime - $buildStartTime

if ($LASTEXITCODE -eq 0) {
    Write-Success "Build Tauri concluÃ­do em $($buildDuration.TotalMinutes.ToString('0.0')) minutos"
}
else {
    Write-Host "âœ— Build Tauri falhou!" -ForegroundColor Red
    exit 1
}

if ($EffectiveBackendUrl) {
    $compiledAssets = Get-ChildItem -Path "dist\public\assets" -Filter "*.js" -Recurse -ErrorAction SilentlyContinue
    $compiledBackendUrl = $compiledAssets | Select-String -Pattern ([regex]::Escape($EffectiveBackendUrl)) -Quiet
    if (-not $compiledBackendUrl) {
        Write-Host "âœ— O Tauri recompilou o frontend sem a URL do backend: $EffectiveBackendUrl" -ForegroundColor Red
        exit 1
    }
    Write-Success "URL do backend confirmada no app: $EffectiveBackendUrl"
}

# ============================================================================
# PASSO 6: Verificar artefatos
# ============================================================================

Write-Header "6. Verificando Artefatos"

$expectedMsiPrefix = if ($Channel -eq "debug") { "WMT Desktop Debug_$currentVersion" } else { "WMT Desktop_$currentVersion" }
$msiPath = Get-ChildItem -Path "src-tauri\target\release\bundle\msi" -Filter "*.msi" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "$expectedMsiPrefix*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $msiPath) {
    $msiPath = Get-ChildItem -Path "src-tauri\target\release" -Filter "*.msi" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "$expectedMsiPrefix*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
$sigPath = if ($msiPath) { "$msiPath.sig" } else { "" }
$portableExePath = Get-ChildItem -Path "src-tauri\target\release" -Filter "wmt-desktop.exe" -File -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName

$files = @($msiPath, $sigPath, $portableExePath) | Where-Object { $_ }

foreach ($file in $files) {
    if (Test-Path $file) {
        $size = (Get-Item $file).Length / 1MB
        Write-Success "$file ($([Math]::Round($size, 1)) MB)"
    }
    else {
        Write-Warning-Custom "NÃ£o encontrado: $file"
    }
}

if (-not $msiPath -or -not (Test-Path $msiPath)) {
    Write-Host "âœ— MSI nÃ£o encontrado para o canal '$Channel' com prefixo '$expectedMsiPrefix'. Verifique se src-tauri/tauri.conf.json usa a identidade correta e bundle.targets = ['msi']." -ForegroundColor Red
    exit 1
}

# ============================================================================
# PASSO 7: Testar MSI (opcional)
# ============================================================================

if (-not $SkipTest) {
    Write-Header "7. Testando MSI Localmente"

    $testResponse = Read-Host "Deseja testar a instalaÃ§Ã£o do MSI? (y/n) [n]"

    if ($testResponse -eq 'y') {
        Write-Info "Abrindo: $msiPath"
        Start-Process -FilePath $msiPath -Wait
        Write-Info "Teste concluÃ­do. VocÃª pode desinstalar o app agora se desejar."
    }
    else {
        Write-Info "Teste pulado"
    }
}

# ============================================================================
# PASSO 8: Preparar Release
# ============================================================================

Write-Header "8. Preparando Release"

$releaseDir = if ($Channel -eq "debug") { ".\releases\debug\$currentVersion" } else { ".\releases\$currentVersion" }

if (-not (Test-Path $releaseDir)) {
    mkdir $releaseDir -Force | Out-Null
    Write-Success "DiretÃ³rio criado: $releaseDir"
}

$releaseMsiLeaf = Split-Path $msiPath -Leaf
$releaseSigLeaf = if ($sigPath -and (Test-Path $sigPath)) { Split-Path $sigPath -Leaf } else { "" }
if ($Channel -eq "debug") {
    $releaseMsiLeaf = $releaseMsiLeaf -replace "\.msi$", "-debug.msi"
    if ($releaseSigLeaf) {
        $releaseSigLeaf = "$releaseMsiLeaf.sig"
    }
}

# Copiar arquivos
Copy-Item $msiPath -Destination (Join-Path $releaseDir $releaseMsiLeaf) -Force
if ($sigPath -and (Test-Path $sigPath)) {
    Copy-Item $sigPath -Destination (Join-Path $releaseDir $releaseSigLeaf) -Force
}
if ($portableExePath -and (Test-Path $portableExePath)) {
    Copy-Item $portableExePath -Destination $releaseDir -Force
}

Write-Success "Arquivos copiados para: $releaseDir"

if ($EffectiveBackendUrl -and $sigPath -and (Test-Path $sigPath)) {
    $updatesDir = ".\backend\data\updates"
    New-Item -ItemType Directory -Path $updatesDir -Force | Out-Null

    $latestJsonName = if ($Channel -eq "debug") { "latest-debug.json" } else { "latest.json" }
    $msiLeaf = Split-Path $msiPath -Leaf
    $sigLeaf = Split-Path $sigPath -Leaf
    if ($Channel -eq "debug") {
        $msiLeaf = $msiLeaf -replace "\.msi$", "-debug.msi"
        $sigLeaf = "$msiLeaf.sig"
    }
    Copy-Item $msiPath -Destination (Join-Path $updatesDir $msiLeaf) -Force
    Copy-Item $sigPath -Destination (Join-Path $updatesDir $sigLeaf) -Force

    $signature = (Get-Content $sigPath -Raw).Trim()
    $encodedMsiLeaf = [Uri]::EscapeDataString($msiLeaf)
    $updatePayload = [ordered]@{
        version = $currentVersion
        notes = $effectiveReleaseNotes
        pub_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        platforms = [ordered]@{
            "windows-x86_64" = [ordered]@{
                signature = $signature
                url = "$EffectiveBackendUrl/api/updates/$encodedMsiLeaf"
            }
        }
    }
    $latestJsonPath = Join-Path $updatesDir $latestJsonName
    $updatePayload | ConvertTo-Json -Depth 10 | Out-File $latestJsonPath -Encoding UTF8
    Copy-Item $latestJsonPath -Destination $releaseDir -Force
    Write-Success "Update publicado em: $updatesDir"
    Write-Success "${latestJsonName}: $EffectiveBackendUrl/api/updates/$latestJsonName"
}
elseif ($EffectiveBackendUrl) {
    Write-Warning-Custom "Update nÃ£o publicado porque o arquivo .sig nÃ£o foi encontrado."
}

# Criar arquivo de release notes
$releaseNotesPath = "$releaseDir\RELEASE_NOTES.md"
@"
# WMT Desktop v$currentVersion

**Data:** $(Get-Date -Format "dd/MM/yyyy")
**Canal:** $Channel

## Notas da atualizacao

$effectiveReleaseNotes
"@ | Out-File $releaseNotesPath
Write-Success "RELEASE_NOTES.md criado com as notas informadas."

# ============================================================================
# PASSO 9: InstruÃ§Ãµes Finais
# ============================================================================

Write-Header "9. PrÃ³ximos Passos"

$finalMessage = @(
    "Build concluido com sucesso!",
    "",
    "CANAL:    $Channel",
    "ARQUIVOS PRONTOS:",
    "  MSI:      $releaseDir\$releaseMsiLeaf",
    "  Assin.:   $(if ($sigPath -and (Test-Path $sigPath)) { "$releaseDir\$releaseSigLeaf" } else { "nao gerada" })",
    "  Portavel: $(if ($portableExePath -and (Test-Path $portableExePath)) { "$releaseDir\$(Split-Path $portableExePath -Leaf)" } else { "nao copiado" })",
    "",
    "PROXIMAS ACOES:",
    "",
    "1. EDITAR RELEASE NOTES",
    "   Abra e complete:",
    "   $releaseNotesPath",
    "",
    "2. FAZER COMMIT (Git)",
    "   git add .",
    "   git commit -m `"Bump version to $currentVersion`"",
    "   git tag v$currentVersion",
    "   git push origin v$currentVersion",
    "",
    "3. DISTRIBUIR MSI",
    "   Copiar: $releaseDir\*",
    "",
    "4. NOTIFICAR USUARIOS",
    "   Enviar link para download do MSI",
    "",
    "5. AUTO-UPDATE",
    "   Se configurado, usuarios receberao atualizacao automatica"
) -join [Environment]::NewLine

Write-Host $finalMessage -ForegroundColor Green

Write-Success "Build & Release preparado! ðŸŽ‰"

Restore-ProductionTauriConfig
