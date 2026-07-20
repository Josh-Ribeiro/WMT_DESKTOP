param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
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

function Invoke-TargetCommand {
    param(
        [string]$ComputerName,
        [scriptblock]$ScriptBlock,
        [object[]]$ArgumentList = @()
    )

    if (Test-LocalHost -ComputerName $ComputerName) {
        & $ScriptBlock @ArgumentList
        return
    }

    $sessionOption = New-PSSessionOption -OpenTimeout 5000 -OperationTimeout 45000
    Invoke-Command -ComputerName $ComputerName -ScriptBlock $ScriptBlock -ArgumentList $ArgumentList -SessionOption $sessionOption
}

function Invoke-ConfigMgrSchedules {
    param(
        [string]$ComputerName,
        [array]$Schedules
    )

    $script = {
        param($RemoteSchedules)

        $client = [wmiclass]"root\ccm:SMS_Client"
        foreach ($schedule in $RemoteSchedules) {
            $client.TriggerSchedule($schedule.Id) | Out-Null
            Write-Output "ConfigMgr: $($schedule.Name) acionado."
        }
    }

    if (Test-LocalHost -ComputerName $ComputerName) {
        & $script $Schedules
        return
    }

    $sessionOption = New-PSSessionOption -OpenTimeout 5000 -OperationTimeout 45000
    Invoke-Command -ComputerName $ComputerName -ScriptBlock $script -ArgumentList (, $Schedules) -SessionOption $sessionOption
}

$normalizedAction = $Action.Trim().ToLowerInvariant()

try {
    if ($normalizedAction -eq "clear-sccm-cache") {
        Invoke-TargetCommand -ComputerName $HostName -ScriptBlock {
            $cachePath = Join-Path $env:windir "ccmcache"
            if (-not (Test-Path -LiteralPath $cachePath)) {
                Write-Output "Cache SCCM nao encontrado em $cachePath."
                return
            }

            $service = Get-Service -Name "CcmExec" -ErrorAction SilentlyContinue
            if ($service -and $service.Status -ne "Stopped") {
                Stop-Service -Name "CcmExec" -Force -ErrorAction Stop
            }

            Get-ChildItem -LiteralPath $cachePath -Force -ErrorAction SilentlyContinue |
                Remove-Item -Force -Recurse -ErrorAction SilentlyContinue

            if ($service) {
                Start-Service -Name "CcmExec" -ErrorAction SilentlyContinue
            }

            Write-Output "Cache SCCM limpo em $cachePath."
        }

        Write-Output "Cache SCCM limpo em $HostName."
        exit 0
    }

    if ($normalizedAction -ne "force-all-actions") {
        throw "Acao de Configuration Manager desconhecida: $Action"
    }

    $schedules = @(
        @{ Name = "Machine Policy Retrieval"; Id = "{00000000-0000-0000-0000-000000000021}" },
        @{ Name = "Machine Policy Evaluation"; Id = "{00000000-0000-0000-0000-000000000022}" },
        @{ Name = "Application Deployment Evaluation"; Id = "{00000000-0000-0000-0000-000000000121}" },
        @{ Name = "Discovery Data Collection"; Id = "{00000000-0000-0000-0000-000000000003}" },
        @{ Name = "Hardware Inventory"; Id = "{00000000-0000-0000-0000-000000000001}" },
        @{ Name = "Software Inventory"; Id = "{00000000-0000-0000-0000-000000000002}" },
        @{ Name = "Software Updates Scan"; Id = "{00000000-0000-0000-0000-000000000113}" },
        @{ Name = "Software Updates Deployment Evaluation"; Id = "{00000000-0000-0000-0000-000000000108}" }
    )

    Invoke-ConfigMgrSchedules -ComputerName $HostName -Schedules $schedules

    Write-Output "Todas as actions do Configuration Manager foram acionadas em $HostName."
}
catch {
    $message = $_.Exception.Message
    if ($message -match "Access is denied|System Error 5|Acesso negado|Access denied") {
        throw "Acesso negado pelo Windows ao executar '$Action' em '$HostName'. O backend deve rodar com uma conta que seja administradora local no computador de destino. Detalhe original: $message"
    }
    throw
}
