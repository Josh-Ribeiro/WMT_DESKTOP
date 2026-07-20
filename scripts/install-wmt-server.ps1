#Requires -RunAsAdministrator
<#
.SYNOPSIS
Installs WMT on a Windows Server host.

.DESCRIPTION
This script is meant to be executed from the WMT repository folder on the target
server. It copies the application to an install root, creates the Python venv,
installs backend dependencies, registers the backend as a startup Scheduled Task,
and configures an IIS site with Windows Authentication and URL Rewrite proxying.

URL Rewrite and ARR are external IIS extensions. The script can try winget with
-InstallIisExtensions, but in locked-down environments you may need to install
them manually before running the IIS part.

.EXAMPLE
.\scripts\install-wmt-server.ps1 -PublicUrl "http://WKS048-51BR" -ServiceAccount "GROUP\svc_wmt"

.EXAMPLE
.\scripts\install-wmt-server.ps1 -PublicUrl "https://wmt.company.local" -SiteName "WMT" -HostHeader "wmt.company.local" -BuildFrontend
#>

param(
    [string]$InstallRoot = "C:\WMT",
    [string]$PublicUrl = "http://$env:COMPUTERNAME",
    [string]$SiteName = "WMT",
    [string]$HostHeader = "",
    [ValidateSet("http", "https")]
    [string]$Protocol = "http",
    [int]$SitePort = 80,
    [string]$CertificateThumbprint = "",
    [int]$BackendPort = 8000,
    [string]$ServiceAccount = "",
    [switch]$RunAsSystem,
    [switch]$BuildFrontend,
    [switch]$InstallIisExtensions,
    [string]$SsoAllowedGroups = "",
    [string]$SsoAdminGroups = "",
    [string]$SsoOperatorGroups = "",
    [string]$SsoDefaultRole = "viewer",
    [switch]$SkipIis
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n== $Message ==" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "WARN $Message" -ForegroundColor Yellow
}

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Resolve-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Copy-WmtTree {
    param(
        [string]$SourceRoot,
        [string]$TargetRoot
    )

    $resolvedSource = (Resolve-Path $SourceRoot).Path.TrimEnd("\")
    $resolvedTarget = if (Test-Path $TargetRoot) { (Resolve-Path $TargetRoot).Path.TrimEnd("\") } else { $TargetRoot.TrimEnd("\") }
    if ($resolvedSource.Equals($resolvedTarget, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Warn "SourceRoot e InstallRoot sao a mesma pasta. Pulando etapa de copia."
        return
    }

    New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
    foreach ($folder in @("backend", "scripts", "dist")) {
        $src = Join-Path $SourceRoot $folder
        if (Test-Path $src) {
            $dst = Join-Path $TargetRoot $folder
            if (Test-Path $dst) {
                Remove-Item -LiteralPath $dst -Recurse -Force
            }
            Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
        }
    }

    foreach ($file in @("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "vite.config.ts", "tsconfig.json", "tsconfig.node.json")) {
        $src = Join-Path $SourceRoot $file
        if (Test-Path $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $TargetRoot $file) -Force
        }
    }

    $clientSrc = Join-Path $SourceRoot "client"
    if ($BuildFrontend -and (Test-Path $clientSrc)) {
        $clientDst = Join-Path $TargetRoot "client"
        if (Test-Path $clientDst) {
            Remove-Item -LiteralPath $clientDst -Recurse -Force
        }
        Copy-Item -LiteralPath $clientSrc -Destination $clientDst -Recurse -Force
    }
}

function Ensure-PythonVenv {
    param(
        [string]$TargetRoot
    )

    if (-not (Test-Command "python")) {
        throw "Python nao encontrado no PATH. Instale Python 3.11+ no servidor e rode novamente."
    }

    $venvPath = Join-Path $TargetRoot ".venv"
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        & python -m venv $venvPath
    }

    $pipExe = Join-Path $venvPath "Scripts\pip.exe"
    & $pythonExe -m pip install --upgrade pip
    & $pipExe install -r (Join-Path $TargetRoot "backend\requirements.txt")
    return $pythonExe
}

function Build-Frontend {
    param(
        [string]$TargetRoot,
        [string]$ApiBaseUrl
    )

    if (-not (Test-Command "pnpm")) {
        throw "pnpm nao encontrado. Instale Node.js + pnpm ou rode sem -BuildFrontend usando um dist/public ja gerado."
    }

    Push-Location $TargetRoot
    try {
        $env:VITE_API_BASE_URL = $ApiBaseUrl.TrimEnd("/")
        & pnpm install
        & pnpm build
    }
    finally {
        Pop-Location
    }
}

function Register-BackendTask {
    param(
        [string]$TargetRoot,
        [string]$PythonExe,
        [string]$TaskName
    )

    $backendDir = Join-Path $TargetRoot "backend"
    $backendMain = Join-Path $backendDir "main.py"
    $arguments = "-u `"$backendMain`""
    $action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $backendDir
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    if ($RunAsSystem) {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest | Out-Null
        Write-Warn "Backend registrado como SYSTEM. Acoes remotas podem falhar sem permissao de rede."
    }
    else {
        $credential = if ($ServiceAccount) {
            Get-Credential -UserName $ServiceAccount -Message "Senha da conta que vai rodar o backend WMT"
        }
        else {
            Get-Credential -Message "Conta AD/servico que vai rodar o backend WMT"
        }
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $credential.UserName -Password ($credential.GetNetworkCredential().Password) -RunLevel Highest | Out-Null
    }

    Start-ScheduledTask -TaskName $TaskName
}

function Set-MachineEnv {
    param(
        [string]$PublicUrlValue,
        [string]$AllowedGroups,
        [string]$AdminGroups,
        [string]$OperatorGroups,
        [string]$DefaultRole
    )

    [Environment]::SetEnvironmentVariable("WMT_SSO_ENABLED", "true", "Machine")
    [Environment]::SetEnvironmentVariable("WMT_SSO_TRUSTED_PROXY_IPS", "127.0.0.1,::1", "Machine")
    [Environment]::SetEnvironmentVariable("WMT_SSO_DEFAULT_ROLE", $DefaultRole, "Machine")
    [Environment]::SetEnvironmentVariable("WMT_CORS_ORIGINS", $PublicUrlValue.TrimEnd("/"), "Machine")

    if ($AllowedGroups) {
        [Environment]::SetEnvironmentVariable("WMT_SSO_ALLOWED_GROUPS", $AllowedGroups, "Machine")
    }
    if ($AdminGroups) {
        [Environment]::SetEnvironmentVariable("WMT_SSO_ADMIN_GROUPS", $AdminGroups, "Machine")
    }
    if ($OperatorGroups) {
        [Environment]::SetEnvironmentVariable("WMT_SSO_OPERATOR_GROUPS", $OperatorGroups, "Machine")
    }
}

function Install-IisFeatures {
    if (Get-Command Install-WindowsFeature -ErrorAction SilentlyContinue) {
        Install-WindowsFeature Web-Server, Web-Mgmt-Console, Web-Windows-Auth, Web-Static-Content, Web-Default-Doc, Web-Http-Errors, Web-Filtering | Out-Null
    }
    else {
        Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole, IIS-WebServer, IIS-ManagementConsole, IIS-WindowsAuthentication, IIS-StaticContent, IIS-DefaultDocument, IIS-HttpErrors, IIS-RequestFiltering -All -NoRestart | Out-Null
    }
}

function Try-InstallIisExtensions {
    if (-not $InstallIisExtensions) {
        return
    }
    if (-not (Test-Command "winget")) {
        Write-Warn "winget nao encontrado. Instale manualmente IIS URL Rewrite e Application Request Routing."
        return
    }

    foreach ($packageId in @("Microsoft.IIS.URLRewrite", "Microsoft.IIS.ApplicationRequestRouting")) {
        try {
            winget install --id $packageId --silent --accept-package-agreements --accept-source-agreements
        }
        catch {
            Write-Warn "Nao foi possivel instalar $packageId via winget: $($_.Exception.Message)"
        }
    }
}

function Add-AllowedServerVariable {
    param([string]$Name)

    $appcmd = Join-Path $env:windir "System32\inetsrv\appcmd.exe"
    if (-not (Test-Path $appcmd)) {
        return
    }
    $current = & $appcmd list config -section:system.webServer/rewrite/allowedServerVariables 2>$null
    if (($current -join "`n") -notmatch [regex]::Escape($Name)) {
        & $appcmd set config -section:system.webServer/rewrite/allowedServerVariables /+"[name='$Name']" /commit:apphost | Out-Null
    }
}

function Configure-IisSite {
    param(
        [string]$TargetRoot,
        [string]$Name,
        [string]$PublicHostHeader,
        [string]$SiteProtocol,
        [int]$Port,
        [string]$CertThumbprint,
        [string]$BackendUrl
    )

    Import-Module WebAdministration -Force

    $sitePath = Join-Path $TargetRoot "dist\public"
    if (-not (Test-Path (Join-Path $sitePath "index.html"))) {
        throw "Frontend nao encontrado em $sitePath. Rode com -BuildFrontend ou copie um dist/public ja gerado."
    }

    $rewriteDll = Join-Path $env:windir "System32\inetsrv\rewrite.dll"
    if (-not (Test-Path $rewriteDll)) {
        Write-Warn "IIS URL Rewrite nao detectado. O site pode falhar ate instalar URL Rewrite + ARR."
    }

    Add-AllowedServerVariable "HTTP_X_REMOTE_USER"
    Add-AllowedServerVariable "HTTP_X_FORWARDED_FOR"
    Add-AllowedServerVariable "HTTP_X_FORWARDED_PROTO"
    Add-AllowedServerVariable "HTTP_X_FORWARDED_HOST"

    if (-not (Test-Path "IIS:\AppPools\$Name")) {
        New-WebAppPool -Name $Name | Out-Null
    }
    Set-ItemProperty "IIS:\AppPools\$Name" -Name managedRuntimeVersion -Value ""

    $existingSite = Get-Website -Name $Name -ErrorAction SilentlyContinue
    if ($existingSite) {
        Stop-Website -Name $Name -ErrorAction SilentlyContinue
        Remove-Website -Name $Name
    }

    $bindingParams = @{
        Name = $Name
        Port = $Port
        PhysicalPath = $sitePath
        ApplicationPool = $Name
    }
    if ($PublicHostHeader) {
        $bindingParams.HostHeader = $PublicHostHeader
    }
    if ($SiteProtocol -eq "https") {
        $bindingParams.Ssl = $true
    }
    New-Website @bindingParams | Out-Null

    if ($SiteProtocol -eq "https") {
        if ($CertThumbprint) {
            $cert = Get-Item "Cert:\LocalMachine\My\$CertThumbprint" -ErrorAction SilentlyContinue
            if (-not $cert) {
                Write-Warn "Certificado $CertThumbprint nao encontrado em LocalMachine\My. Configure o binding HTTPS manualmente."
            }
            else {
                $bindingPath = if ($PublicHostHeader) { "IIS:\SslBindings\0.0.0.0!$Port!$PublicHostHeader" } else { "IIS:\SslBindings\0.0.0.0!$Port" }
                if (Test-Path $bindingPath) {
                    Remove-Item $bindingPath -Force
                }
                if ($PublicHostHeader) {
                    $cert | New-Item $bindingPath -SSLFlags 1 | Out-Null
                }
                else {
                    $cert | New-Item $bindingPath | Out-Null
                }
            }
        }
        else {
            Write-Warn "Site criado em HTTPS, mas sem -CertificateThumbprint. Configure o certificado no IIS antes de usar."
        }
    }

    Set-WebConfigurationProperty -PSPath "IIS:\Sites\$Name" -Filter "/system.webServer/security/authentication/windowsAuthentication" -Name enabled -Value $true
    Set-WebConfigurationProperty -PSPath "IIS:\Sites\$Name" -Filter "/system.webServer/security/authentication/anonymousAuthentication" -Name enabled -Value $false

    $proto = if ($SiteProtocol -eq "https") { "https" } else { "http" }
    $webConfigPath = Join-Path $sitePath "web.config"
    $webConfig = @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <defaultDocument>
      <files>
        <clear />
        <add value="index.html" />
      </files>
    </defaultDocument>
    <rewrite>
      <rules>
        <rule name="WMT API to backend" stopProcessing="true">
          <match url="^api/(.*)$" />
          <action type="Rewrite" url="$BackendUrl/api/{R:1}" />
          <serverVariables>
            <set name="HTTP_X_REMOTE_USER" value="{LOGON_USER}" />
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
            <set name="HTTP_X_FORWARDED_PROTO" value="$proto" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
          </serverVariables>
        </rule>
        <rule name="WMT SPA fallback" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="/index.html" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"@
    $webConfig | Out-File -FilePath $webConfigPath -Encoding UTF8 -Force
    Start-Website -Name $Name
}

function Test-BackendHealth {
    param([int]$Port)

    $healthUrl = "http://127.0.0.1:$Port/api/health"
    for ($i = 0; $i -lt 20; $i++) {
        try {
            Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 | Out-Null
            Write-Ok "Backend respondeu em $healthUrl"
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Warn "Backend ainda nao respondeu em $healthUrl. Verifique a tarefa agendada e logs."
}

$repoRoot = Resolve-RepoRoot
$backendUrl = "http://127.0.0.1:$BackendPort"
$taskName = "WMT Backend"

Write-Step "1. Copiando aplicacao"
Copy-WmtTree -SourceRoot $repoRoot -TargetRoot $InstallRoot
Write-Ok "Arquivos copiados para $InstallRoot"

if ($BuildFrontend) {
    Write-Step "2. Buildando frontend para $PublicUrl"
    Build-Frontend -TargetRoot $InstallRoot -ApiBaseUrl $PublicUrl
}
elseif (-not (Test-Path (Join-Path $InstallRoot "dist\public\index.html"))) {
    throw "dist/public nao existe. Rode pnpm build antes de copiar ou execute este script com -BuildFrontend."
}

Write-Step "3. Preparando backend Python"
$pythonExe = Ensure-PythonVenv -TargetRoot $InstallRoot
Write-Ok "Venv pronto: $pythonExe"

Write-Step "4. Configurando variaveis de ambiente"
Set-MachineEnv -PublicUrlValue $PublicUrl -AllowedGroups $SsoAllowedGroups -AdminGroups $SsoAdminGroups -OperatorGroups $SsoOperatorGroups -DefaultRole $SsoDefaultRole
Write-Ok "Variaveis WMT configuradas em Machine"

Write-Step "5. Registrando backend"
Register-BackendTask -TargetRoot $InstallRoot -PythonExe $pythonExe -TaskName $taskName
Test-BackendHealth -Port $BackendPort

if (-not $SkipIis) {
    Write-Step "6. Configurando IIS"
    Install-IisFeatures
    Try-InstallIisExtensions
    Configure-IisSite -TargetRoot $InstallRoot -Name $SiteName -PublicHostHeader $HostHeader -SiteProtocol $Protocol -Port $SitePort -CertThumbprint $CertificateThumbprint -BackendUrl $backendUrl
    Write-Ok "IIS configurado: $PublicUrl"
}

Write-Step "Resumo"
Write-Host @"
WMT instalado.

InstallRoot: $InstallRoot
Backend:     $backendUrl
Site:        $PublicUrl
Task:        $taskName

Proximos checks:
  1. Abra $PublicUrl no servidor.
  2. Acesse de outra maquina do dominio.
  3. Confirme Windows Authentication e /api/health via IIS.
  4. Se o IIS mostrar erro de rewrite, instale IIS URL Rewrite + ARR e rode novamente.
"@ -ForegroundColor Green
