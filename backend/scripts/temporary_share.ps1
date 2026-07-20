param(
    [string]$wks,
    [ValidateSet("create", "remove")]
    [string]$action,
    [int]$ttlMinutes = 30,
    [string]$driveLetter = "C"
)

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$driveLetter = ($driveLetter -replace "[:\\/\s]", "").ToUpper()
if ($driveLetter -notmatch "^[A-Z]$") {
    $driveLetter = "C"
}

$shareName = "WMT_TEMP_${driveLetter}`$"
$sharePath = "${driveLetter}:\"
$description = "Temporary WMT access to $driveLetter drive"
$cleanupTaskPath = "\WMT\"
$cleanupTaskName = "TemporaryShare-$($shareName -replace '[^A-Za-z0-9_-]', '_')"
$cleanupTaskFullName = "$cleanupTaskPath$cleanupTaskName"

function Write-JsonAndExit {
    param(
        [hashtable]$Payload,
        [int]$ExitCode = 0
    )

    $Payload | ConvertTo-Json -Compress
    exit $ExitCode
}

function Get-ShareReturnMessage {
    param([int]$Code)

    switch ($Code) {
        0 { "Success" }
        2 { "Access denied" }
        8 { "Unknown failure" }
        9 { "Invalid name" }
        10 { "Invalid level" }
        21 { "Invalid parameter" }
        22 { "Duplicate share" }
        23 { "Redirected path" }
        24 { "Unknown device or directory" }
        25 { "Net name not found" }
        default { "ReturnValue=$Code" }
    }
}

function Get-RemoteShare {
    param([string]$ComputerName)

    Get-WmiObject -Class Win32_Share -ComputerName $ComputerName -Filter "Name='$shareName'" -ErrorAction Stop
}

function Set-ShareFullControl {
    param([string]$ComputerName)

    $trustee = ([WmiClass]"\\$ComputerName\root\cimv2:Win32_Trustee").CreateInstance()
    $trustee.SID = [byte[]](1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0)

    $ace = ([WmiClass]"\\$ComputerName\root\cimv2:Win32_ACE").CreateInstance()
    $ace.AccessMask = [uint32]2032127
    $ace.AceFlags = [uint32]0
    $ace.AceType = [uint32]0
    $ace.Trustee = $trustee

    $securityDescriptor = ([WmiClass]"\\$ComputerName\root\cimv2:Win32_SecurityDescriptor").CreateInstance()
    $securityDescriptor.ControlFlags = [uint32]4
    $securityDescriptor.DACL = @($ace)

    $shareSecurity = Get-WmiObject `
        -Class Win32_LogicalShareSecuritySetting `
        -ComputerName $ComputerName `
        -Filter "Name='$shareName'" `
        -ErrorAction Stop

    $result = $shareSecurity.SetSecurityDescriptor($securityDescriptor)
    if ([int]$result.ReturnValue -ne 0) {
        throw "Failed to set share permissions. $(Get-ShareReturnMessage -Code ([int]$result.ReturnValue))"
    }
}

function Invoke-RemotePowerShell {
    param(
        [string]$ComputerName,
        [string]$Script
    )

    $bytes = [System.Text.Encoding]::Unicode.GetBytes($Script)
    $encoded = [Convert]::ToBase64String($bytes)
    $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
    $result = Invoke-WmiMethod -Class Win32_Process -Name Create -ComputerName $ComputerName -ArgumentList $command -ErrorAction Stop
    if ([int]$result.ReturnValue -ne 0) {
        throw "Failed to start remote PowerShell. $(Get-ShareReturnMessage -Code ([int]$result.ReturnValue))"
    }
}

function Set-CleanupTask {
    param(
        [string]$ComputerName,
        [int]$TtlSeconds
    )

    $runAt = (Get-Date).AddSeconds($TtlSeconds).ToString("o")
    $script = @"
`$ErrorActionPreference = 'Stop'
`$taskPath = '$cleanupTaskPath'
`$taskName = '$cleanupTaskName'
Unregister-ScheduledTask -TaskPath `$taskPath -TaskName `$taskName -Confirm:`$false -ErrorAction SilentlyContinue
`$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c net share $shareName /delete /y >nul 2>nul'
`$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]'$runAt')
`$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
`$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -Compatibility Win8
Register-ScheduledTask -TaskPath `$taskPath -TaskName `$taskName -Action `$action -Trigger `$trigger -Principal `$principal -Settings `$settings -Force | Out-Null
"@
    Invoke-RemotePowerShell -ComputerName $ComputerName -Script $script
}

function Remove-CleanupTask {
    param([string]$ComputerName)

    $script = @"
Unregister-ScheduledTask -TaskPath '$cleanupTaskPath' -TaskName '$cleanupTaskName' -Confirm:`$false -ErrorAction SilentlyContinue
"@
    Invoke-RemotePowerShell -ComputerName $ComputerName -Script $script
}

if ($wks -match "^\d{1,3}(\.\d{1,3}){3}$") {
    try {
        $hostname = ([System.Net.Dns]::GetHostEntry($wks).HostName)
        $wks = $hostname.Split(".")[0]
    }
    catch {
    }
}

if (-not (Test-Connection $wks -Count 1 -Quiet)) {
    Write-JsonAndExit @{
        erro = "Host is offline or unreachable"
        Hostname = $wks
        Action = $action
    } 1
}

try {
    if ($ttlMinutes -lt 1) { $ttlMinutes = 1 }
    if ($ttlMinutes -gt 240) { $ttlMinutes = 240 }

    if ($action -eq "create") {
        $existing = Get-RemoteShare -ComputerName $wks

        if (-not $existing) {
            $shareClass = [WmiClass]"\\$wks\root\cimv2:Win32_Share"
            $createResult = $shareClass.Create(
                $sharePath,
                $shareName,
                [uint32]0
            )

            if ([int]$createResult.ReturnValue -ne 0) {
                throw "Failed to create share. $(Get-ShareReturnMessage -Code ([int]$createResult.ReturnValue))"
            }
        }

        Set-ShareFullControl -ComputerName $wks

        $ttlSeconds = [Math]::Max(60, $ttlMinutes * 60)
        $cleanupWarning = ""
        try {
            Set-CleanupTask -ComputerName $wks -TtlSeconds $ttlSeconds
        }
        catch {
            $cleanupWarning = $_.Exception.Message
        }

        Write-JsonAndExit @{
            Success = $true
            Hostname = $wks
            Action = $action
            ShareName = $shareName
            SharePath = $sharePath
            UncPath = "\\$wks\$shareName"
            TtlMinutes = $ttlMinutes
            ExpiresAt = (Get-Date).AddMinutes($ttlMinutes).ToString("yyyy-MM-dd HH:mm:ss")
            CleanupTaskName = $cleanupTaskFullName
            CleanupWarning = $cleanupWarning
            Message = "Temporary share is available"
            AlreadyExisted = [bool]$existing
        }
    }

    if ($action -eq "remove") {
        try {
            Remove-CleanupTask -ComputerName $wks
        }
        catch {
        }
        $existing = Get-RemoteShare -ComputerName $wks

        if (-not $existing) {
            Write-JsonAndExit @{
                Success = $true
                Hostname = $wks
                Action = $action
                ShareName = $shareName
                UncPath = "\\$wks\$shareName"
                CleanupTaskName = $cleanupTaskFullName
                Message = "Temporary share was already removed"
                Removed = $false
            }
        }

        $deleteResult = $existing.Delete()
        if ([int]$deleteResult.ReturnValue -ne 0) {
            throw "Failed to remove share. $(Get-ShareReturnMessage -Code ([int]$deleteResult.ReturnValue))"
        }

        Write-JsonAndExit @{
            Success = $true
            Hostname = $wks
            Action = $action
            ShareName = $shareName
            UncPath = "\\$wks\$shareName"
            CleanupTaskName = $cleanupTaskFullName
            Message = "Temporary share removed"
            Removed = $true
        }
    }
}
catch {
    Write-JsonAndExit @{
        erro = $_.Exception.Message
        Hostname = $wks
        Action = $action
        ShareName = $shareName
    } 1
}
