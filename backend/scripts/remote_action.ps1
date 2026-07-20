param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [string]$Action,

    [int]$TtlMinutes = 60
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

function Start-RemoteCleanupTask {
    param(
        [string]$ComputerName,
        [string]$ShareName,
        [string]$TaskName,
        [int]$CleanupDelaySeconds
    )

    $runAt = (Get-Date).AddSeconds($CleanupDelaySeconds).ToString("o")
    $cleanupScript = @"
`$ErrorActionPreference = 'Stop'
`$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c net share "$ShareName" /delete /y >nul 2>nul & schtasks /Delete /TN "$TaskName" /F >nul 2>nul'
`$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]'$runAt')
Register-ScheduledTask -TaskName '$TaskName' -Action `$action -Trigger `$trigger -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cleanupScript))
    $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
    $result = Invoke-WmiMethod -Class Win32_Process -Name Create -ComputerName $ComputerName -ArgumentList $command
    if ([int]$result.ReturnValue -ne 0) {
        throw "Falha ao iniciar agendamento da remocao. ReturnValue=$($result.ReturnValue)"
    }
}

$normalizedAction = $Action.Trim().ToLowerInvariant()
$TtlMinutes = [Math]::Max(1, [Math]::Min(240, $TtlMinutes))
$ttlSeconds = $TtlMinutes * 60

try {
    switch ($normalizedAction) {
        "remote-access" {
            Write-Output "Remote Desktop deve ser aberto no app desktop do usuario para $HostName."
        }
        "remote-assistance" {
            Write-Output "Remote Assistance deve ser aberto no app desktop do usuario para $HostName."
        }
        "admin-share" {
            Write-Output "Admin share disponivel em \\$HostName\c$."
        }
        "computer-management" {
            Write-Output "Computer Management deve ser aberto no app desktop do usuario para $HostName."
        }
        "gpupdate" {
            Invoke-TargetCommand -ComputerName $HostName -ScriptBlock {
                gpupdate.exe /force
            }
            Write-Output "GPUpdate executado em $HostName."
        }
        "restart-spooler" {
            Invoke-TargetCommand -ComputerName $HostName -ScriptBlock {
                Restart-Service -Name "Spooler" -Force
                Get-Service -Name "Spooler" | Select-Object -Property Name, Status
            }
            Write-Output "Spooler reiniciado em $HostName."
        }
        "renew-ip" {
            Invoke-TargetCommand -ComputerName $HostName -ScriptBlock {
                $adapters = @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.Status -eq "Up" -and
                        $_.HardwareInterface -eq $true -and
                        $_.InterfaceDescription -notmatch "Virtual|Hyper-V|VMware|Loopback|Bluetooth|TAP|VPN"
                    })

                if (-not $adapters.Count) {
                    ipconfig.exe /flushdns | Out-Null
                    Write-Output "Nenhum adaptador fisico ativo encontrado. DNS foi limpo."
                    return
                }

                foreach ($adapter in $adapters) {
                    Write-Output "Reiniciando adaptador: $($adapter.Name)"
                    Disable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
                    Start-Sleep -Seconds 2
                    Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
                }

                $deadline = (Get-Date).AddSeconds(20)
                do {
                    Start-Sleep -Seconds 2
                    $ready = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue |
                        Where-Object { $_.IPv4Address -and $_.NetAdapter.Status -eq "Up" })
                    if ($ready.Count -gt 0) {
                        break
                    }
                } while ((Get-Date) -lt $deadline)

                ipconfig.exe /flushdns
                Get-NetIPConfiguration | Select-Object InterfaceAlias, IPv4Address, DNSServer
            }
            Write-Output "Adaptador de rede reiniciado e cache DNS limpo em $HostName."
        }
        "create-temp-c-share" {
            $shareName = "TempC$"
            $taskName = "WMT_Remove_TempC"
            $existing = Get-WmiObject -Class Win32_Share -ComputerName $HostName -Filter "Name='$shareName'" -ErrorAction Stop

            if ($null -eq $existing) {
                $shareClass = [WmiClass]"\\$HostName\root\cimv2:Win32_Share"
                $createResult = $shareClass.Create("C:\", $shareName, [uint32]0)
                if ([int]$createResult.ReturnValue -notin @(0, 22)) {
                    throw "Falha ao criar share $shareName. ReturnValue=$($createResult.ReturnValue)"
                }
                Write-Output "Share $shareName criada apontando para C:\."
            }
            else {
                Write-Output "Share $shareName ja existe."
            }

            try {
                Start-RemoteCleanupTask -ComputerName $HostName -ShareName $shareName -TaskName $taskName -CleanupDelaySeconds $ttlSeconds
                Write-Output "Remocao automatica agendada para ate $([Math]::Round($ttlSeconds / 60)) minutos."
            }
            catch {
                Write-Warning $_.Exception.Message
            }
            $sharePath = "\\$HostName\TempC$"
            Write-Output "Share temporaria criada em $sharePath por no maximo $TtlMinutes minutos."
        }
        "remove-temp-c-share" {
            Invoke-TargetCommand -ComputerName $HostName -ScriptBlock {
                $shareName = "TempC$"
                $existing = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue

                if ($null -ne $existing) {
                    Remove-SmbShare -Name $shareName -Force
                    Write-Output "Share $shareName removida."
                }
                else {
                    Write-Output "Share $shareName nao existe."
                }

                Unregister-ScheduledTask -TaskName "WMT_Remove_TempC" -Confirm:$false -ErrorAction SilentlyContinue
            }
            Write-Output "Share temporaria removida de $HostName."
        }
        default {
            throw "Acao remota desconhecida: $Action"
        }
    }
}
catch {
    $message = $_.Exception.Message
    if ($message -match "Access is denied|System Error 5|Acesso negado|Access denied") {
        throw "Acesso negado pelo Windows ao executar '$Action' em '$HostName'. O backend deve rodar com uma conta que seja administradora local no computador de destino. Detalhe original: $message"
    }
    throw
}
