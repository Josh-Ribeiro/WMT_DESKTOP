#Requires -Version 7.0
<#
.SYNOPSIS
Script completo: Build + Version + Release para WMT Desktop

.PARAMETER Type
"major", "minor", "patch" ou vazio para não mudar versão

.PARAMETER SkipTest
Se true, pula somente a abertura manual do MSI. As verificacoes automatizadas
de qualidade e seguranca nunca sao ignoradas.

.PARAMETER BackendUrl
URL HTTPS do backend usada pelo app empacotado. Ex: https://wmt.empresa.local

.PARAMETER UpdateEndpoint
Endpoint do updater. Se omitido, usa BackendUrl + /api/updates/latest.json

.PARAMETER Channel
Canal de release: prod usa latest.json; debug usa latest-debug.json e instala lado a lado

.PARAMETER BackendMode
central usa somente BackendUrl; sidecar empacota e inicia o backend local

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
    [ValidateSet("central", "sidecar")]
    [string]$BackendMode = "central",
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
        "  .\build-and-release.ps1 -BackendUrl https://wmt.empresa.local",
        "  .\build-and-release.ps1 -BackendUrl https://wmt.empresa.local -UpdateEndpoint https://wmt.empresa.local/api/updates/latest.json",
        "  .\build-and-release.ps1 -Channel debug -BackendUrl http://127.0.0.1:8000 -UpdateEndpoint https://wmt.empresa.local/api/updates/latest-debug.json",
        "",
        "OPCOES:",
        "  -Type [major|minor|patch]  Tipo de versionamento (opcional)",
        "  -BackendUrl                URL do backend para o app empacotado",
        "  -UpdateEndpoint            URL do latest.json para auto-update",
        "  -Channel [prod|debug]      Canal do update; debug instala separado e usa latest-debug.json",
        "  -BackendMode              central (padrao) ou sidecar",
        "  -ReleaseNotes              Texto exibido no aviso de atualizacao",
        "  -ReleaseNotesFile          Arquivo TXT/Markdown com as notas da atualizacao",
        "  -SkipReleaseNotesPrompt    Nao pergunta as notas durante o build",
        "  -SkipTest                  Pula somente a instalacao manual do MSI",
        "  -Help                      Mostra esta ajuda",
        "",
        "EXEMPLOS:",
        "  .\build-and-release.ps1 -Type patch",
        "  .\build-and-release.ps1 -Type minor",
        "  .\build-and-release.ps1",
        "  .\build-and-release.ps1 -Type patch -ReleaseNotes ""Busca universal mais rapida e correcoes no monitor.""",
        "  .\build-and-release.ps1 -Type patch -ReleaseNotesFile .\notas.md",
        "  .\build-and-release.ps1 -BackendUrl https://wmt.empresa.local",
        "  .\build-and-release.ps1 -BackendUrl https://wmt.empresa.local -UpdateEndpoint https://wmt.empresa.local/api/updates/latest.json",
        "  .\build-and-release.ps1 -BackendMode sidecar -Channel debug -UpdateEndpoint https://wmt.empresa.local/api/updates/latest-debug.json",
        "  .\build-and-release.ps1 -Channel debug -BackendUrl http://127.0.0.1:8000 -UpdateEndpoint https://wmt.empresa.local/api/updates/latest-debug.json"
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
elseif ($EffectiveBackendUrl -and $BackendMode -eq "central") {
    $latestFileName = if ($Channel -eq "debug") { "latest-debug.json" } else { "latest.json" }
    $EffectiveUpdateEndpoint = "$EffectiveBackendUrl/api/updates/$latestFileName"
}

function Test-LoopbackUrl {
    param([string]$Url)
    try {
        $uri = [Uri]$Url
        return $uri.Host -in @("localhost", "127.0.0.1", "::1")
    }
    catch {
        return $false
    }
}

function Test-PlaceholderUrl {
    param([string]$Url)
    if (-not $Url) {
        return $false
    }
    try {
        $uri = [Uri]$Url
        return $uri.Host -eq "example.com" -or $uri.Host.EndsWith(".example.com", [System.StringComparison]::OrdinalIgnoreCase)
    }
    catch {
        return $false
    }
}

if ($BackendMode -eq "sidecar") {
    if ($BackendUrl -and -not (Test-LoopbackUrl $BackendUrl)) {
        throw "BackendMode sidecar aceita somente BackendUrl de loopback."
    }
    $EffectiveBackendUrl = "http://127.0.0.1:8000"
    $env:VITE_API_BASE_URL = $EffectiveBackendUrl
}

if ($EffectiveBackendUrl -and -not $EffectiveBackendUrl.StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) {
    $allowedLoopback = ($Channel -eq "debug" -or $BackendMode -eq "sidecar") -and (Test-LoopbackUrl $EffectiveBackendUrl)
    if (-not $allowedLoopback) {
        throw "BackendUrl deve usar HTTPS. HTTP e permitido somente para loopback em debug/sidecar."
    }
}
if ($EffectiveUpdateEndpoint -and -not $EffectiveUpdateEndpoint.StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "UpdateEndpoint deve usar HTTPS."
}

$updaterPrivateKeyPath = Resolve-Path ".\secrets\wmt-updater.key" -ErrorAction SilentlyContinue
if ($updaterPrivateKeyPath) {
    $env:TAURI_SIGNING_PRIVATE_KEY = $updaterPrivateKeyPath.Path
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
    Write-Info "Chave privada do updater configurada: $($updaterPrivateKeyPath.Path)"
}
else {
    Write-Warning-Custom "Chave do updater não encontrada em .\secrets\wmt-updater.key"
}

# ============================================================================
# PASSO 1: Preparar ambiente
# ============================================================================

Write-Header "1. Verificando Ambiente"

$tauriConfPath = ".\src-tauri\tauri.conf.json"
$packagePath = ".\package.json"
$cargoTomlPath = ".\src-tauri\Cargo.toml"
$backendConfigPath = ".\backend\app\core\config.py"
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
    $tauriConf.app.security.csp = $tauriConfProdSnapshot.app.security.csp
    $tauriConf.plugins.updater.dangerousInsecureTransportProtocol = $tauriConfProdSnapshot.plugins.updater.dangerousInsecureTransportProtocol
    $tauriConf.bundle.createUpdaterArtifacts = $tauriConfProdSnapshot.bundle.createUpdaterArtifacts
    if ($tauriConfProdSnapshot.bundle.PSObject.Properties.Name -contains "externalBin") {
        $tauriConf.bundle.externalBin = $tauriConfProdSnapshot.bundle.externalBin
    }
    elseif ($tauriConf.bundle.PSObject.Properties.Name -contains "externalBin") {
        $tauriConf.bundle.PSObject.Properties.Remove("externalBin")
    }
    $tauriConf | ConvertTo-Json -Depth 20 | Out-File $tauriConfPath -Encoding UTF8
    $script:DebugTauriConfigApplied = $false
    Write-Success "Config Tauri de producao restaurada apos build debug."
}

trap {
    Restore-ProductionTauriConfig
    throw $_
}

if ($Channel -eq "prod" -and $BackendMode -eq "central") {
    if (-not $EffectiveBackendUrl) {
        throw "Build de produção central exige -BackendUrl com a URL HTTPS real do servidor."
    }
    if (Test-PlaceholderUrl $EffectiveBackendUrl) {
        throw "BackendUrl de produção não pode usar o domínio reservado example.com."
    }
}
if (Test-PlaceholderUrl $EffectiveUpdateEndpoint) {
    throw "UpdateEndpoint não pode usar o domínio reservado example.com."
}

if (-not (Test-Path $tauriConfPath)) {
    Write-Host "✗ Arquivo não encontrado: $tauriConfPath" -ForegroundColor Red
    exit 1
}

# Ler versão atual
$tauriConf = Get-Content $tauriConfPath -Raw | ConvertFrom-Json
$currentVersion = $tauriConf.version
Write-Success "Versão atual: $currentVersion"

# Verificar dependências
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
        Write-Warning-Custom "$($check.Key): NÃO ENCONTRADO"
    }
}

# ============================================================================
# PASSO 2: Bumpar versão (se solicitado)
# ============================================================================

if ($Type) {
    Write-Header "2. Bumpar Versão"

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
    Write-Info "Atualizando versão: $currentVersion → $newVersion"

    $tauriConf.version = $newVersion
    $tauriConf | ConvertTo-Json -Depth 10 | Out-File $tauriConfPath -Encoding UTF8

    $package = Get-Content $packagePath -Raw | ConvertFrom-Json
    $package.version = $newVersion
    $package | ConvertTo-Json -Depth 10 | Out-File $packagePath -Encoding UTF8

    $cargoToml = Get-Content $cargoTomlPath -Raw
    $cargoToml = $cargoToml -replace '(?m)^(version\s*=\s*")[^"]+(")', "`${1}$newVersion`${2}"
    Set-Content $cargoTomlPath -Value $cargoToml -Encoding UTF8

    $backendConfig = Get-Content $backendConfigPath -Raw
    $backendConfig = $backendConfig -replace 'APP_VERSION = os\.getenv\("WMT_VERSION", "[^"]+"\)\.strip\(\) or "[^"]+"', "APP_VERSION = os.getenv(`"WMT_VERSION`", `"$newVersion`").strip() or `"$newVersion`""
    Set-Content $backendConfigPath -Value $backendConfig -Encoding UTF8

    $currentVersion = $newVersion
    Write-Success "Versão atualizada para $newVersion"
}
else {
    Write-Info "Versão: $currentVersion (não será alterada)"
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
        $tauriConf.plugins.updater.dangerousInsecureTransportProtocol = $false
        $tauriConf.bundle.createUpdaterArtifacts = $true
    }
    $connectSources = @(
        "'self'",
        "ipc:",
        "http://ipc.localhost",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "ws://localhost:5173"
    )
    foreach ($configuredUrl in @($EffectiveBackendUrl, $EffectiveUpdateEndpoint)) {
        if (-not $configuredUrl) {
            continue
        }
        $configuredUri = [Uri]$configuredUrl
        $origin = $configuredUri.GetLeftPart([System.UriPartial]::Authority)
        if ($origin -notin $connectSources) {
            $connectSources += $origin
        }
    }
    $connectSourceText = $connectSources -join " "
    $tauriConf.app.security.csp = "default-src 'self' customprotocol: asset:; connect-src $connectSourceText; img-src 'self' asset: data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
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

$env:WMT_BACKEND_MODE = $BackendMode
if ($BackendMode -eq "sidecar") {
    Write-Header "Preparando backend sidecar"
    & "$PSScriptRoot\build-backend-sidecar.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao gerar o backend sidecar."
    }
    $tauriConf = Get-Content $tauriConfPath -Raw | ConvertFrom-Json
    $tauriConf.bundle | Add-Member -NotePropertyName externalBin -NotePropertyValue @("binaries/wmt-backend") -Force
    $tauriConf | ConvertTo-Json -Depth 20 | Out-File $tauriConfPath -Encoding UTF8
    $script:DebugTauriConfigApplied = $true
    Write-Success "Backend sidecar sera incluido no MSI."
}
else {
    Write-Info "Modo central: o Tauri nao iniciara backend local."
}

# ============================================================================
# PASSO 3: Instalar dependências
# ============================================================================

Write-Header "3. Instalando Dependências"

Write-Info "Executando: pnpm install --frozen-lockfile"
& pnpm install --frozen-lockfile
Write-Success "Dependências instaladas"

Write-Header "4. Quality Gate"
& "$PSScriptRoot\verify.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "As verificacoes automaticas falharam. O release foi interrompido."
}
Write-Success "Todas as verificacoes automaticas passaram"

# ============================================================================
# PASSO 5: Build Frontend
# ============================================================================

Write-Header "5. Build do Frontend"

Write-Info "Compilando React + TypeScript + Tailwind..."
if ($EffectiveBackendUrl) {
    Write-Info "Backend configurado no app: $EffectiveBackendUrl"
}
else {
    Write-Warning-Custom "Backend do app ficará no padrão: http://127.0.0.1:8000"
}
& pnpm build
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Build frontend falhou!" -ForegroundColor Red
    exit 1
}
if ($EffectiveBackendUrl) {
    $compiledAssets = Get-ChildItem -Path "dist\public\assets" -Filter "*.js" -Recurse -ErrorAction SilentlyContinue
    $compiledBackendUrl = $compiledAssets | Select-String -Pattern ([regex]::Escape($EffectiveBackendUrl)) -Quiet
    if (-not $compiledBackendUrl) {
        Write-Host "✗ A URL do backend não foi embutida no frontend compilado: $EffectiveBackendUrl" -ForegroundColor Red
        exit 1
    }
}
Write-Success "Frontend compilado"

# ============================================================================
# PASSO 6: Build Tauri (Main Build)
# ============================================================================

Write-Header "6. Build do Tauri (MAIN - vai levar um tempo)"

Write-Info "Compilando Rust + empacotando MSI..."
Write-Info "Tempo estimado: 5-10 minutos (primeira vez: 30-45 min)"

$buildStartTime = Get-Date
& pnpm build:tauri
$buildEndTime = Get-Date
$buildDuration = $buildEndTime - $buildStartTime

if ($LASTEXITCODE -eq 0) {
    Write-Success "Build Tauri concluído em $($buildDuration.TotalMinutes.ToString('0.0')) minutos"
}
else {
    Write-Host "✗ Build Tauri falhou!" -ForegroundColor Red
    exit 1
}

if ($EffectiveBackendUrl) {
    $compiledAssets = Get-ChildItem -Path "dist\public\assets" -Filter "*.js" -Recurse -ErrorAction SilentlyContinue
    $compiledBackendUrl = $compiledAssets | Select-String -Pattern ([regex]::Escape($EffectiveBackendUrl)) -Quiet
    if (-not $compiledBackendUrl) {
        Write-Host "✗ O Tauri recompilou o frontend sem a URL do backend: $EffectiveBackendUrl" -ForegroundColor Red
        exit 1
    }
    Write-Success "URL do backend confirmada no app: $EffectiveBackendUrl"
}

# ============================================================================
# PASSO 7: Verificar artefatos
# ============================================================================

Write-Header "7. Verificando Artefatos"

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
        Write-Warning-Custom "Não encontrado: $file"
    }
}

if (-not $msiPath -or -not (Test-Path $msiPath)) {
    Write-Host "✗ MSI não encontrado para o canal '$Channel' com prefixo '$expectedMsiPrefix'. Verifique se src-tauri/tauri.conf.json usa a identidade correta e bundle.targets = ['msi']." -ForegroundColor Red
    exit 1
}

# ============================================================================
# PASSO 8: Testar MSI (opcional)
# ============================================================================

if (-not $SkipTest) {
    Write-Header "8. Testando MSI Localmente"

    $testResponse = Read-Host "Deseja testar a instalação do MSI? (y/n) [n]"

    if ($testResponse -eq 'y') {
        Write-Info "Abrindo: $msiPath"
        Start-Process -FilePath $msiPath -Wait
        Write-Info "Teste concluído. Você pode desinstalar o app agora se desejar."
    }
    else {
        Write-Info "Teste pulado"
    }
}

# ============================================================================
# PASSO 9: Preparar Release
# ============================================================================

Write-Header "9. Preparando Release"

$releaseDir = if ($Channel -eq "debug") { ".\releases\debug\$currentVersion" } else { ".\releases\$currentVersion" }

if (-not (Test-Path $releaseDir)) {
    mkdir $releaseDir -Force | Out-Null
    Write-Success "Diretório criado: $releaseDir"
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
    Write-Warning-Custom "Update não publicado porque o arquivo .sig não foi encontrado."
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
# PASSO 10: Instruções Finais
# ============================================================================

Write-Header "10. Próximos Passos"

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
