param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [string[]]$UserNames
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Invoke-Command -ComputerName $HostName -ArgumentList (,$UserNames) -ScriptBlock {
    param([string[]]$UserNames)

    $sids = @(
        foreach ($userName in $UserNames) {
            $account = if ($userName -match "\\") { $userName } else { "$env:USERDOMAIN\$userName" }
            ([System.Security.Principal.NTAccount]$account).
                Translate([System.Security.Principal.SecurityIdentifier]).
                Value
        }
    ) | Sort-Object -Unique

    $suffix = [guid]::NewGuid().ToString("N")
    $configPath = Join-Path $env:TEMP "wmt-rights-remove-$suffix.inf"
    $databasePath = Join-Path $env:TEMP "wmt-rights-remove-$suffix.sdb"
    secedit.exe /export /cfg $configPath /areas USER_RIGHTS /quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao exportar os direitos locais. Código: $LASTEXITCODE"
    }

    $lines = @(Get-Content -LiteralPath $configPath -Encoding Unicode)
    foreach ($right in @("SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight")) {
        for ($index = 0; $index -lt $lines.Count; $index++) {
            if ($lines[$index] -notlike "$right*") { continue }
            $current = @(($lines[$index] -split "=", 2)[1] -split "," |
                ForEach-Object { $_.Trim() } |
                Where-Object { $_ })
            $remove = @($sids | ForEach-Object { "*$_" })
            $remaining = @($current | Where-Object { $_ -notin $remove })
            $lines[$index] = "$right = $($remaining -join ',')"
            break
        }
    }

    Set-Content -LiteralPath $configPath -Value $lines -Encoding Unicode
    secedit.exe /configure /db $databasePath /cfg $configPath /areas USER_RIGHTS /quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao restaurar os direitos locais. Código: $LASTEXITCODE"
    }

    Remove-Item $configPath, $databasePath -Force -ErrorAction SilentlyContinue
    [pscustomobject]@{
        computer = $env:COMPUTERNAME
        users = $UserNames
        removed_sids = $sids
    }
} | ConvertTo-Json -Compress
