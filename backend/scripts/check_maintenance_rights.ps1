param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [string]$UserName
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Invoke-Command -ComputerName $HostName -ArgumentList $UserName -ScriptBlock {
    param($UserName)

    $account = if ($UserName -match "\\") { $UserName } else { "$env:USERDOMAIN\$UserName" }
    $sid = ([System.Security.Principal.NTAccount]$account).
        Translate([System.Security.Principal.SecurityIdentifier]).
        Value

    $configPath = Join-Path $env:TEMP "wmt-rights-check.inf"
    secedit.exe /export /cfg $configPath /areas USER_RIGHTS /quiet | Out-Null
    $lines = @(Get-Content -LiteralPath $configPath -Encoding Unicode)
    Remove-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue

    $local = [string]($lines |
        Where-Object { $_ -like "SeDenyInteractiveLogonRight*" } |
        Select-Object -First 1)
    $remote = [string]($lines |
        Where-Object { $_ -like "SeDenyRemoteInteractiveLogonRight*" } |
        Select-Object -First 1)

    [pscustomobject]@{
        user = $account
        sid = $sid
        maintenance_active = Test-Path "C:\ProgramData\TI\ModoManutencao\ativo.flag"
        config_exists = Test-Path "C:\ProgramData\TI\ModoManutencao\config.json"
        denied_interactive = $local -like "*$sid*"
        denied_remote_interactive = $remote -like "*$sid*"
        local_right = $local
        remote_right = $remote
    }
} | Select-Object user, sid, maintenance_active, config_exists, denied_interactive,
    denied_remote_interactive, local_right, remote_right |
    ConvertTo-Json -Compress
