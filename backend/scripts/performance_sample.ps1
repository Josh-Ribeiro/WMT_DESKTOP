param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$Action = "sample"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

function Convert-BytesToGb {
    param([double]$Value)
    if (-not $Value) { return 0 }
    return [math]::Round($Value / 1GB, 2)
}

function Round-Number {
    param([object]$Value, [int]$Digits = 1)
    if ($null -eq $Value -or $Value -eq "") { return 0 }
    return [math]::Round([double]$Value, $Digits)
}

function Invoke-Remote {
    param([scriptblock]$ScriptBlock)

    $localNames = @("localhost", "127.0.0.1", ".", $env:COMPUTERNAME)
    if ($localNames -contains $HostName) {
        & $ScriptBlock
        return
    }

    $sessionOption = New-PSSessionOption -OpenTimeout 5000 -OperationTimeout 30000
    Invoke-Command -ComputerName $HostName -ScriptBlock $ScriptBlock -SessionOption $sessionOption
}

$sample = Invoke-Remote {
    $ErrorActionPreference = "Stop"

    function Convert-BytesToGb {
        param([double]$Value)
        if (-not $Value) { return 0 }
        return [math]::Round($Value / 1GB, 2)
    }

    function Round-Number {
        param([object]$Value, [int]$Digits = 1)
        if ($null -eq $Value -or $Value -eq "") { return 0 }
        return [math]::Round([double]$Value, $Digits)
    }

    $cpuPerf = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $logicalDisks = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3")
    $networkCounters = @(Get-CimInstance -ClassName Win32_PerfFormattedData_Tcpip_NetworkInterface | Where-Object {
        $_.Name -notmatch "Loopback|isatap|Teredo" -and ([double]($_.BytesTotalPersec -as [double]) -ge 0)
    })

    $disks = @($logicalDisks | ForEach-Object {
        $size = [double]($_.Size -as [double])
        $free = [double]($_.FreeSpace -as [double])
        $used = [math]::Max(0, $size - $free)
        [ordered]@{
            name = $_.DeviceID
            label = [string]$_.VolumeName
            size_gb = Convert-BytesToGb $size
            free_gb = Convert-BytesToGb $free
            used_gb = Convert-BytesToGb $used
            usage_percent = $(if ($size -gt 0) { Round-Number (($used / $size) * 100) } else { 0 })
        }
    })

    $diskSize = [double](($logicalDisks | Measure-Object -Property Size -Sum).Sum)
    $diskFree = [double](($logicalDisks | Measure-Object -Property FreeSpace -Sum).Sum)
    $diskUsed = [math]::Max(0, $diskSize - $diskFree)

    $interfaces = @($networkCounters | Sort-Object -Property BytesTotalPersec -Descending | Select-Object -First 8 | ForEach-Object {
        [ordered]@{
            name = [string]$_.Name
            bytes_per_sec = [double]($_.BytesTotalPersec -as [double])
            received_bytes_per_sec = [double]($_.BytesReceivedPersec -as [double])
            sent_bytes_per_sec = [double]($_.BytesSentPersec -as [double])
        }
    })

    $temperatureSensors = @()
    $temperatureMessage = ""
    try {
        $thermalZones = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop)
        $temperatureSensors = @($thermalZones | Where-Object { $_.CurrentTemperature } | ForEach-Object {
            $celsius = Round-Number ((([double]$_.CurrentTemperature / 10) - 273.15)) 1
            [ordered]@{
                name = [string]$_.InstanceName
                type = "ACPI Thermal Zone"
                celsius = $celsius
                fahrenheit = Round-Number (($celsius * 9 / 5) + 32) 1
            }
        })
        if (-not $temperatureSensors.Count) {
            $temperatureMessage = "Nenhum sensor de temperatura foi exposto pelo Windows neste host."
        }
    }
    catch {
        $temperatureMessage = "Temperatura indisponivel via WMI neste host."
    }

    $memoryTotalKb = [double]$os.TotalVisibleMemorySize
    $memoryFreeKb = [double]$os.FreePhysicalMemory
    $memoryUsedKb = [math]::Max(0, $memoryTotalKb - $memoryFreeKb)

    [ordered]@{
        host = $env:COMPUTERNAME
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        cpu = [ordered]@{
            usage_percent = Round-Number $cpuPerf.PercentProcessorTime
            queue_length = 0
        }
        memory = [ordered]@{
            total_gb = Round-Number ($memoryTotalKb / 1MB) 2
            used_gb = Round-Number ($memoryUsedKb / 1MB) 2
            free_gb = Round-Number ($memoryFreeKb / 1MB) 2
            usage_percent = $(if ($memoryTotalKb -gt 0) { Round-Number (($memoryUsedKb / $memoryTotalKb) * 100) } else { 0 })
        }
        disk = [ordered]@{
            total_gb = Convert-BytesToGb $diskSize
            used_gb = Convert-BytesToGb $diskUsed
            free_gb = Convert-BytesToGb $diskFree
            usage_percent = $(if ($diskSize -gt 0) { Round-Number (($diskUsed / $diskSize) * 100) } else { 0 })
            volumes = $disks
        }
        network = [ordered]@{
            bytes_per_sec = [double](($interfaces | Measure-Object -Property bytes_per_sec -Sum).Sum)
            received_bytes_per_sec = [double](($interfaces | Measure-Object -Property received_bytes_per_sec -Sum).Sum)
            sent_bytes_per_sec = [double](($interfaces | Measure-Object -Property sent_bytes_per_sec -Sum).Sum)
            interfaces = $interfaces
        }
        temperatures = [ordered]@{
            available = [bool]($temperatureSensors.Count -gt 0)
            message = $temperatureMessage
            sensors = $temperatureSensors
        }
    }
}

$sample.requested_host = $HostName
$sample | ConvertTo-Json -Depth 8
