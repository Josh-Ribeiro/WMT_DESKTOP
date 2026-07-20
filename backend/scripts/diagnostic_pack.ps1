param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [switch]$RunCleanup,

    [switch]$IncludeDetails
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

function New-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message = "",
        [object]$Data = $null
    )

    [ordered]@{
        name = $Name
        status = $Status
        message = $Message
        data = $Data
    }
}

function Invoke-Remote {
    param(
        [scriptblock]$ScriptBlock,
        [object[]]$ArgumentList = @()
    )

    $localNames = @("localhost", "127.0.0.1", ".", $env:COMPUTERNAME)
    if ($localNames -contains $HostName) {
        & $ScriptBlock @ArgumentList
        return
    }

    $sessionOption = New-PSSessionOption -OpenTimeout 5000 -OperationTimeout 60000
    Invoke-Command -ComputerName $HostName -ScriptBlock $ScriptBlock -ArgumentList $ArgumentList -SessionOption $sessionOption
}

function Test-TcpPortFast {
    param(
        [string]$ComputerName,
        [int]$Port,
        [int]$TimeoutMs = 700
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

$checks = New-Object System.Collections.Generic.List[object]
$startedAt = Get-Date

$online = Test-Connection -ComputerName $HostName -Count 1 -Quiet
$checks.Add((New-Check "Ping" ($(if ($online) { "ok" } else { "fail" })) ($(if ($online) { "Host respondeu ao ping." } else { "Host nao respondeu ao ping." }))))

foreach ($port in @(445, 135, 5985)) {
    try {
        $tcp = Test-TcpPortFast -ComputerName $HostName -Port $port
        $label = switch ($port) {
            445 { "SMB 445" }
            135 { "RPC 135" }
            5985 { "WinRM 5985" }
        }
        $checks.Add((New-Check $label ($(if ($tcp) { "ok" } else { "fail" })) ($(if ($tcp) { "Porta acessivel." } else { "Porta indisponivel ou bloqueada." }))))
    }
    catch {
        $checks.Add((New-Check "Port $port" "warn" $_.Exception.Message))
    }
}

try {
    $payload = Invoke-Remote -ArgumentList @([bool]$RunCleanup, [bool]($IncludeDetails -or $RunCleanup)) -ScriptBlock {
        param([bool]$DoCleanup, [bool]$LoadDetails)

        $errors = New-Object System.Collections.Generic.List[string]
        try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch { $os = $null; $errors.Add("OS: $($_.Exception.Message)") }
        try { $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop } catch { $computer = $null; $errors.Add("Computer: $($_.Exception.Message)") }
        try { $bios = Get-CimInstance Win32_BIOS -ErrorAction Stop } catch { $bios = $null; $errors.Add("BIOS: $($_.Exception.Message)") }
        try {
            $disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop |
                Select-Object DeviceID,
                    @{Name="SizeGB"; Expression={[math]::Round($_.Size / 1GB, 1)}},
                    @{Name="FreeGB"; Expression={[math]::Round($_.FreeSpace / 1GB, 1)}}
        }
        catch {
            $disks = @()
            $errors.Add("Disks: $($_.Exception.Message)")
        }
        $software = @()
        if ($LoadDetails) {
            foreach ($path in @(
                "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
                "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
            )) {
                $software += Get-ItemProperty $path -ErrorAction SilentlyContinue |
                    Where-Object { $_.DisplayName } |
                    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate
            }
            $software = $software |
                Sort-Object DisplayName -Unique |
                Select-Object -First 120
        }

        $bitlocker = @()
        if (Get-Command Get-BitLockerVolume -ErrorAction SilentlyContinue) {
            $bitlocker = Get-BitLockerVolume -ErrorAction SilentlyContinue |
                Select-Object MountPoint, VolumeStatus, ProtectionStatus, EncryptionPercentage
        }

        $cleanupPreview = [ordered]@{}
        $cleanupTargets = @()
        if ($LoadDetails) {
            $cleanupTargets = @($env:TEMP, "C:\Windows\Temp")
            $cleanupTargets += @(Get-ChildItem "C:\Users" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                @(
                    (Join-Path $_.FullName "AppData\Local\Google\Chrome\User Data\Default\Cache"),
                    (Join-Path $_.FullName "AppData\Local\Google\Chrome\User Data\Default\Code Cache"),
                    (Join-Path $_.FullName "AppData\Local\Microsoft\Edge\User Data\Default\Cache"),
                    (Join-Path $_.FullName "AppData\Local\Microsoft\Edge\User Data\Default\Code Cache")
                )
            })
            $cleanupTargets += @("C:\Windows\Logs\CBS", "C:\Windows\Logs\DISM")
        }
        $existingCleanupTargets = New-Object System.Collections.Generic.List[string]
        foreach ($target in ($cleanupTargets | Select-Object -Unique)) {
            if (-not $target) { continue }
            try {
                if (Test-Path -LiteralPath $target -ErrorAction Stop) {
                    $existingCleanupTargets.Add([string]$target)
                }
            }
            catch {
            }
        }
        $cleanupTargets = @($existingCleanupTargets.ToArray())

        foreach ($path in $cleanupTargets) {
            try {
                $items = Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue
                $files = @($items | Where-Object { -not $_.PSIsContainer })
                $cleanupPreview[$path] = [ordered]@{
                    items = @($items).Count
                    size_mb = [math]::Round((($files | ForEach-Object { [int64]($_.Length) } | Measure-Object -Sum).Sum) / 1MB, 1)
                }
            }
            catch {
                $cleanupPreview[$path] = [ordered]@{ error = $_.Exception.Message }
            }
        }

        $cleanup = [ordered]@{}
        if ($DoCleanup) {
            foreach ($path in $cleanupTargets) {
                $removed = 0
                try {
                    Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue |
                        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) -or $path -match "Cache|Code Cache|Temp" } |
                        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
                    $removed = 1
                }
                catch {
                }
                $cleanup[$path] = if ($removed) { "cleanup requested" } else { "cleanup skipped or failed" }
            }
            try {
                Clear-RecycleBin -Force -ErrorAction SilentlyContinue
                $cleanup["RecycleBin"] = "cleanup requested"
            }
            catch {
                $cleanup["RecycleBin"] = "cleanup skipped or failed"
            }
        }

        [ordered]@{
            os = [ordered]@{
                caption = if ($os) { $os.Caption } else { "" }
                version = if ($os) { $os.Version } else { "" }
                build = if ($os) { $os.BuildNumber } else { "" }
                architecture = if ($os) { $os.OSArchitecture } else { "" }
                last_boot = if ($os) { $os.LastBootUpTime } else { "" }
                uptime_hours = if ($os) { [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1) } else { 0 }
            }
            computer = [ordered]@{
                manufacturer = if ($computer) { $computer.Manufacturer } else { "" }
                model = if ($computer) { $computer.Model } else { "" }
                memory_gb = if ($computer) { [math]::Round($computer.TotalPhysicalMemory / 1GB, 1) } else { 0 }
                serial = if ($bios) { $bios.SerialNumber } else { "" }
                logged_user = if ($computer) { $computer.UserName } else { "" }
            }
            disks = @($disks)
            bitlocker = @($bitlocker)
            software = @($software)
            cleanup_preview = $cleanupPreview
            cleanup = $cleanup
            errors = @($errors.ToArray())
        }
    }

    if ($payload.errors -and @($payload.errors).Count -gt 0) {
        $checks.Add((New-Check "Inventario" "warn" ("Inventario parcial: " + (($payload.errors | Select-Object -First 2) -join " | "))))
    }
    else {
        $checks.Add((New-Check "Inventario" "ok" "Inventario coletado com sucesso."))
    }
}
catch {
    $payload = [ordered]@{}
    $checks.Add((New-Check "Inventario" "fail" ("Line $($_.InvocationInfo.ScriptLineNumber): $($_.Exception.Message)")))
}

[ordered]@{
    host = $HostName
    generated_at = (Get-Date).ToString("s")
    duration_ms = [int](((Get-Date) - $startedAt).TotalMilliseconds)
    checks = @($checks.ToArray())
    inventory = $payload
} | ConvertTo-Json -Depth 8 -Compress
