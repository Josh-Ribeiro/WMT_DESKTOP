#Requires -RunAsAdministrator
<#
.SYNOPSIS
Testa configuração de Windows Auth no IIS + Backend SSO

.PARAMETER BackendUrl
URL do backend (default: "http://127.0.0.1:8000")

.PARAMETER SiteName
Nome do site IIS (default: "Default Web Site")

.PARAMETER User
Usuário para teste (default: $env:USERNAME)

.EXAMPLE
.\test-iis-windows-auth.ps1 -BackendUrl "http://127.0.0.1:8000"
#>

param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$SiteName = "Default Web Site",
    [string]$User = $env:USERNAME
)

function Write-Header {
    param([string]$Message)
    Write-Host "`n========== $Message ==========" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ $Message" -ForegroundColor Blue
}

Import-Module WebAdministration -Force

# 1. Verificar IIS
Write-Header "1. Verificando IIS"

$site = Get-IISSite -Name $SiteName -ErrorAction SilentlyContinue
if ($null -eq $site) {
    Write-Error-Custom "Site '$SiteName' não encontrado"
    exit 1
}
Write-Success "Site '$SiteName' encontrado"

# 2. Verificar Windows Authentication
Write-Header "2. Verificando Windows Authentication"

$winAuthConfig = Get-WebConfigurationProperty `
    -Filter "/system.webServer/security/authentication/windowsAuthentication" `
    -Name "enabled" `
    -PSPath "IIS:\Sites\$SiteName" `
    -ErrorAction SilentlyContinue

if ($winAuthConfig -eq $true) {
    Write-Success "Windows Authentication está HABILITADO"
} else {
    Write-Error-Custom "Windows Authentication está DESABILITADO"
}

# 3. Verificar Anonymous Auth
Write-Header "3. Verificando Anonymous Authentication"

$anonAuthConfig = Get-WebConfigurationProperty `
    -Filter "/system.webServer/security/authentication/anonymousAuthentication" `
    -Name "enabled" `
    -PSPath "IIS:\Sites\$SiteName" `
    -ErrorAction SilentlyContinue

if ($anonAuthConfig -eq $false) {
    Write-Success "Anonymous Authentication está DESABILITADO (correto)"
} else {
    Write-Error-Custom "Anonymous Authentication está HABILITADO (deve estar desabilitado)"
}

# 4. Verificar Providers
Write-Header "4. Verificando Providers"

$providers = Get-WebConfigurationProperty `
    -Filter "/system.webServer/security/authentication/windowsAuthentication/providers" `
    -Name "Collection" `
    -PSPath "IIS:\Sites\$SiteName" `
    -ErrorAction SilentlyContinue

if ($providers) {
    $providerList = @()
    foreach ($provider in $providers) {
        $providerList += $provider.value
    }
    Write-Success "Providers configurados: $($providerList -join ', ')"
    
    if ($providerList -contains "Negotiate") {
        Write-Success "✓ Negotiate presente (Kerberos)"
    } else {
        Write-Error-Custom "✗ Negotiate não encontrado"
    }
} else {
    Write-Error-Custom "Nenhum provider configurado"
}

# 5. Verificar URL Rewrite
Write-Header "5. Verificando URL Rewrite"

$sitePhysicalPath = $site.PhysicalPath
$webConfigPath = Join-Path $sitePhysicalPath "web.config"

if (Test-Path $webConfigPath) {
    $webConfig = [xml](Get-Content $webConfigPath)
    
    $rewriteRules = $webConfig.configuration.'system.webServer'.rewrite.rules.rule
    
    if ($rewriteRules) {
        Write-Success "Regras de rewrite encontradas"
        
        $rule = $rewriteRules | Where-Object { $_.name -eq "Route to WMT Backend" }
        
        if ($rule) {
            Write-Success "Regra 'Route to WMT Backend' encontrada"
            Write-Info "Padrão: $($rule.match.url)"
            Write-Info "Rewrite URL: $($rule.action.url)"
            
            $serverVars = $rule.serverVariables.set
            if ($serverVars | Where-Object { $_.name -eq "HTTP_X_REMOTE_USER" }) {
                Write-Success "✓ HTTP_X_REMOTE_USER será configurado como {LOGON_USER}"
            } else {
                Write-Error-Custom "✗ HTTP_X_REMOTE_USER não encontrado em ServerVariables"
            }
        } else {
            Write-Error-Custom "Regra 'Route to WMT Backend' não encontrada"
        }
    } else {
        Write-Error-Custom "Nenhuma regra de rewrite encontrada"
    }
} else {
    Write-Error-Custom "web.config não encontrado em $webConfigPath"
}

# 6. Testar Backend
Write-Header "6. Testando conectividade com Backend"

try {
    $response = Invoke-WebRequest -Uri "$BackendUrl/docs" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Success "Backend respondendo em $BackendUrl (Status: $($response.StatusCode))"
} catch {
    Write-Error-Custom "Não foi possível alcançar backend em $BackendUrl"
    Write-Info "Erro: $($_.Exception.Message)"
}

# 7. Testar header com curl
Write-Header "7. Testando X-Remote-User header"

$curlExePath = "C:\Program Files\Git\usr\bin\curl.exe"
if (-not (Test-Path $curlExePath)) {
    $curlExePath = (Get-Command curl -ErrorAction SilentlyContinue).Source
}

if ($curlExePath) {
    Write-Info "Enviando request com header X-Remote-User simulado..."
    
    $domain = $env:USERDOMAIN
    $testUser = "$domain\$User"
    
    try {
        $response = & $curlExePath -s -i -H "X-Remote-User: $testUser" "$BackendUrl/api/auth/sso" 2>&1
        
        if ($response -match "200|401|403") {
            Write-Success "Backend respondeu (não rejeitou header)"
            Write-Info "Resposta: $($response -split "`n" | Select-Object -First 3)"
        } else {
            Write-Error-Custom "Resposta inesperada"
        }
    } catch {
        Write-Error-Custom "Erro ao fazer curl: $($_.Exception.Message)"
    }
} else {
    Write-Info "curl não encontrado, pulando teste de header"
}

# 8. Verificar App Pool
Write-Header "8. Verificando Application Pool"

$appPool = $site.Applications[0].ApplicationPool
if ($appPool) {
    $appPoolStatus = Get-WebAppPoolState -Name $appPool
    Write-Success "Application Pool: $appPool (Status: $($appPoolStatus.Value))"
} else {
    Write-Error-Custom "Application Pool não identificado"
}

# 9. Resumo de diagnóstico
Write-Header "9. Resumo"

$issues = @()

if ($winAuthConfig -ne $true) { $issues += "Windows Authentication desabilitado" }
if ($anonAuthConfig -ne $false) { $issues += "Anonymous Authentication habilitado" }
if (-not $providers) { $issues += "Nenhum provider configurado" }

if ($issues.Count -eq 0) {
    Write-Success "Nenhum problema encontrado! Configuração parece OK."
    Write-Info "Próximo passo: Testar acesso do navegador"
} else {
    Write-Error-Custom "Problemas encontrados:"
    $issues | ForEach-Object { Write-Host "  - $_" }
    Write-Info "Execute .\configure-iis-windows-auth.ps1 para corrigir"
}

Write-Host @"

Comandos úteis para diagnóstico:

# Ver configuração de authentication
Get-WebConfigurationProperty -Filter "/system.webServer/security/authentication" -Name "." | Format-List

# Testar acesso com credenciais
curl -H "Authorization: Negotiate" https://seu-dominio.local/

# Limpar cache de credenciais (se necessário)
cmdkey /list
cmdkey /delete:seu-dominio.local

# Debugar rewrite rules
appcmd list site `"$SiteName`" /text:*

"@ -ForegroundColor DarkGray
