param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [ValidateSet("status", "install-updates")]
    [string]$Action
)

$ErrorActionPreference = "Stop"

function Test-LocalHost {
    param([string]$ComputerName)

    $localNames = @(
        "localhost",
        "127.0.0.1",
        ".",
        $env:COMPUTERNAME
    )

    return $localNames -contains $ComputerName
}

function Invoke-Target {
    param(
        [string]$ComputerName,
        [scriptblock]$ScriptBlock
    )

    if (Test-LocalHost -ComputerName $ComputerName) {
        & $ScriptBlock
        return
    }

    Invoke-Command -ComputerName $ComputerName -ScriptBlock $ScriptBlock
}

$statusScript = {
    $client = Get-CimInstance -Namespace "root\ccm" -ClassName "SMS_Client" -ErrorAction Stop
    $service = Get-Service -Name "CcmExec" -ErrorAction SilentlyContinue
    $updates = @(
        Get-CimInstance -Namespace "root\ccm\ClientSDK" -ClassName "CCM_SoftwareUpdate" -ErrorAction SilentlyContinue |
            Where-Object { $_.ComplianceState -eq 0 }
    )

    [pscustomobject]@{
        installed = $true
        clientVersion = [string]$client.ClientVersion
        serviceStatus = if ($service) { [string]$service.Status } else { "" }
        pendingUpdates = $updates.Count
        updates = @(
            $updates | Select-Object `
                @{ Name = "name"; Expression = { [string]$_.Name } },
                @{ Name = "articleId"; Expression = { [string]$_.ArticleID } },
                @{ Name = "bulletinId"; Expression = { [string]$_.BulletinID } },
                @{ Name = "evaluationState"; Expression = { [int]$_.EvaluationState } },
                @{ Name = "percentComplete"; Expression = { [int]$_.PercentComplete } },
                @{ Name = "errorCode"; Expression = { [int]$_.ErrorCode } }
        )
    }
}

$installScript = {
    $updates = @(
        Get-CimInstance -Namespace "root\ccm\ClientSDK" -ClassName "CCM_SoftwareUpdate" -ErrorAction Stop |
            Where-Object { $_.ComplianceState -eq 0 }
    )

    if ($updates.Count -gt 0) {
        Invoke-CimMethod `
            -Namespace "root\ccm\ClientSDK" `
            -ClassName "CCM_SoftwareUpdatesManager" `
            -MethodName "InstallUpdates" `
            -Arguments @{ CCMUpdates = [CimInstance[]]$updates } | Out-Null
    }

    [pscustomobject]@{
        ok = $true
        pendingUpdates = $updates.Count
        message = if ($updates.Count -gt 0) { "Instalacao iniciada para $($updates.Count) update(s)." } else { "Nenhuma atualizacao pendente encontrada." }
    }
}

try {
    if ($Action -eq "status") {
        $result = Invoke-Target -ComputerName $HostName -ScriptBlock $statusScript
    }
    else {
        $result = Invoke-Target -ComputerName $HostName -ScriptBlock $installScript
    }

    $result | ConvertTo-Json -Depth 5 -Compress
}
catch {
    [pscustomobject]@{
        installed = $false
        clientVersion = ""
        serviceStatus = ""
        pendingUpdates = 0
        updates = @()
        ok = $false
        message = $_.Exception.Message
    } | ConvertTo-Json -Depth 5 -Compress
}
