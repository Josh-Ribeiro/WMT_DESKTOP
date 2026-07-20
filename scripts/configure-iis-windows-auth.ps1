#Requires -RunAsAdministrator
<#
.SYNOPSIS
Configura IIS para Windows Authentication com ARR e URL Rewrite
Passa X-Remote-User para backend FastAPI

.PARAMETER SiteName
Nome do site IIS a configurar (default: "Default Web Site")

.PARAMETER BackendUrl
URL do backend FastAPI (default: "http://127.0.0.1:8000")

.PARAMETER DomainPrefix
Prefixo do domínio (ex: "wmt.empresa.local")

.EXAMPLE
.\configure-iis-windows-auth.ps1 -SiteName "WMT" -BackendUrl "http://127.0.0.1:8000"
#>

param(
    [string]$SiteName = "Default Web Site",
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$DomainPrefix = "wmt.empresa.local"
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

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "⚠ $Message" -ForegroundColor Yellow
}

# 1. Verificar pré-requisitos
Write-Header "1. Verificando pré-requisitos"

$modules = @(
    "WebAdministration",
    "ServerManager"
)

foreach ($module in $modules) {
    if (Get-Module -ListAvailable -Name $module) {
        Write-Success "Módulo $module disponível"
    } else {
        Write-Warning-Custom "Módulo $module não encontrado"
    }
}

# Importar WebAdministration
Import-Module WebAdministration -Force

# 2. Verificar se site existe
Write-Header "2. Verificando site IIS"

$site = Get-IISSite -Name $SiteName -ErrorAction SilentlyContinue

if ($null -eq $site) {
    Write-Warning-Custom "Site '$SiteName' não encontrado. Sites disponíveis:"
    Get-IISSite | Select-Object -ExpandProperty Name
    exit 1
}

Write-Success "Site '$SiteName' encontrado"

# 3. Habilitar Windows Authentication
Write-Header "3. Habilitando Windows Authentication"

$authPath = "IIS:\Sites\$SiteName"

# Windows Authentication
Set-WebConfigurationProperty -Filter "/system.webServer/security/authentication/windowsAuthentication" `
    -Name "enabled" -Value $true -PSPath $authPath -ErrorAction SilentlyContinue

Write-Success "Windows Authentication habilitado"

# Anonymous Authentication
Set-WebConfigurationProperty -Filter "/system.webServer/security/authentication/anonymousAuthentication" `
    -Name "enabled" -Value $false -PSPath $authPath -ErrorAction SilentlyContinue

Write-Success "Anonymous Authentication desabilitado"

# 4. Configurar Windows Auth Providers
Write-Header "4. Configurando Providers"

$providersPath = "IIS:\Sites\$SiteName\App_Data\.config\windowsAuthentication"

# Remover providers antigos
Get-WebConfigurationProperty `
    -Filter "/system.webServer/security/authentication/windowsAuthentication/providers" `
    -Name "Collection" -PSPath $authPath -ErrorAction SilentlyContinue | 
    ForEach-Object {
        Clear-WebConfiguration `
            -Filter "/system.webServer/security/authentication/windowsAuthentication/providers" `
            -PSPath $authPath
    }

# Adicionar Negotiate
Add-WebConfigurationProperty `
    -Filter "/system.webServer/security/authentication/windowsAuthentication/providers" `
    -Name "." -Value @{value="Negotiate"} -PSPath $authPath -ErrorAction SilentlyContinue

Write-Success "Provider 'Negotiate' adicionado"

# Adicionar NTLM
Add-WebConfigurationProperty `
    -Filter "/system.webServer/security/authentication/windowsAuthentication/providers" `
    -Name "." -Value @{value="NTLM"} -PSPath $authPath -ErrorAction SilentlyContinue

Write-Success "Provider 'NTLM' adicionado (fallback)"

# 5. Criar/atualizar web.config com URL Rewrite
Write-Header "5. Configurando URL Rewrite (X-Remote-User)"

$sitePhysicalPath = (Get-IISSite -Name $SiteName).PhysicalPath
$webConfigPath = Join-Path $sitePhysicalPath "web.config"

$webConfigContent = @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    
    <!-- Authentication -->
    <authentication>
      <windowsAuthentication enabled="true">
        <providers>
          <add value="Negotiate" />
          <add value="NTLM" />
        </providers>
      </windowsAuthentication>
      <anonymousAuthentication enabled="false" />
    </authentication>

    <!-- URL Rewrite Rules -->
    <rewrite>
      <rules>
        <rule name="Route to WMT Backend" enabled="true" stopProcessing="true">
          <match url="^(.*)$" />
          <conditions>
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="$BackendUrl/{R:1}" />
          <serverVariables>
            <set name="HTTP_X_REMOTE_USER" value="{LOGON_USER}" />
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
          </serverVariables>
        </rule>
      </rules>
    </rewrite>

  </system.webServer>
</configuration>
"@

# Backup do web.config anterior
if (Test-Path $webConfigPath) {
    $backup = "$webConfigPath.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item $webConfigPath $backup
    Write-Success "Backup anterior salvo: $backup"
}

$webConfigContent | Out-File -FilePath $webConfigPath -Encoding UTF8 -Force
Write-Success "web.config atualizado com regras de rewrite"

# 6. Verificar variáveis de ambiente
Write-Header "6. Variáveis de ambiente SSO"

$ssoVars = @{
    "WMT_SSO_ENABLED" = "true"
    "WMT_SSO_TRUSTED_PROXY_IPS" = "127.0.0.1,::1"
    "WMT_SSO_DEFAULT_ROLE" = "viewer"
}

foreach ($var in $ssoVars.GetEnumerator()) {
    $currentValue = [Environment]::GetEnvironmentVariable($var.Key, "Machine")
    if ($null -eq $currentValue -or $currentValue -eq "") {
        Write-Warning-Custom "$($var.Key) não definida. Considere configurar:"
        Write-Host "  [Environment]::SetEnvironmentVariable('$($var.Key)', '$($var.Value)', 'Machine')"
    } else {
        Write-Success "$($var.Key) = $currentValue"
    }
}

# 7. Reiniciar Site
Write-Header "7. Reciclando Application Pool"

$appPool = (Get-IISSite -Name $SiteName).Applications[0].ApplicationPool
if ($appPool) {
    Restart-WebAppPool -Name $appPool
    Write-Success "Application Pool '$appPool' reciclado"
    Start-Sleep -Seconds 2
} else {
    Write-Warning-Custom "Application Pool não encontrado, restartando site diretamente"
    Restart-IISSite -Name $SiteName
}

# 8. Resumo
Write-Header "8. Resumo e Próximos Passos"

Write-Host @"

✓ Configuração concluída para site: $SiteName

Próximos passos:

1. Configurar Variáveis de Ambiente (se ainda não estão):
   [Environment]::SetEnvironmentVariable('WMT_SSO_ENABLED', 'true', 'Machine')
   [Environment]::SetEnvironmentVariable('WMT_SSO_ALLOWED_GROUPS', 'CN=WMT-Users,OU=Groups,DC=empresa,DC=local', 'Machine')
   [Environment]::SetEnvironmentVariable('WMT_SSO_ADMIN_GROUPS', 'CN=WMT-Admins,OU=Groups,DC=empresa,DC=local', 'Machine')

2. Reiniciar o Backend FastAPI:
   Pare e inicie novamente o processo/serviço do backend

3. Testar com o navegador:
   Acesse: https://$DomainPrefix
   Você deve receber um prompt de autenticação Windows

4. Verificar logs:
   Backend: Procure por "X-Remote-User" nas logs
   IIS: Verifique Failed Request Tracing em:
        %WINDIR%\System32\LogFiles\FailedReqLogFiles

5. Configurar Kerberos SPN (se usar conta de serviço):
   setspn -S HTTP/$DomainPrefix EMPRESA\svc_account
   setspn -L EMPRESA\svc_account

"@ -ForegroundColor Green

Write-Success "Script finalizado"
