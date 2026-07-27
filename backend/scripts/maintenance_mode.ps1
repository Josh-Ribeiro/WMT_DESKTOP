param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [ValidateSet("status", "enable", "disable")]
    [string]$Action = "status",

    [string]$Technician = "Equipe de TI",
    [string]$TechnicianUsername = "",
    [string]$Contact = "Service Desk",
    [string]$Ticket = "",
    [string]$Reason = "",

    [ValidateRange(5, 1440)]
    [int]$DurationMinutes = 60,

    [string]$TargetUser = ""
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Test-LocalHost {
    param([string]$ComputerName)
    return @("localhost", "127.0.0.1", ".", $env:COMPUTERNAME) -contains $ComputerName
}

function Invoke-TargetCommand {
    param([scriptblock]$ScriptBlock, [object[]]$ArgumentList = @())
    if (Test-LocalHost -ComputerName $HostName) {
        & $ScriptBlock @ArgumentList
        return
    }
    $options = New-PSSessionOption -OpenTimeout 5000 -OperationTimeout 90000
    Invoke-Command -ComputerName $HostName -ScriptBlock $ScriptBlock -ArgumentList $ArgumentList -SessionOption $options
}

$cleanupScript = @'
$ErrorActionPreference = "SilentlyContinue"
$BasePath = "C:\ProgramData\TI\ModoManutencao"
$ConfigPath = Join-Path $BasePath "config.json"
$PolicyKey = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization"
$CspKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
$Config = $null
try {
    if (Test-Path $ConfigPath) { $Config = Get-Content $ConfigPath -Raw -ErrorAction Stop | ConvertFrom-Json }
} catch {}

function Set-WmtRegistryState {
    param([string]$Path, [string]$Name, [object]$State)
    if ($State -and $State.Exists) {
        New-Item -Path $Path -Force | Out-Null
        New-ItemProperty -Path $Path -Name $Name -PropertyType ([string]$State.Kind) -Value $State.Value -Force | Out-Null
    } else {
        Remove-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
    }
}

function Remove-WmtDenyRights {
    param([object]$Config)
    if (-not $Config) { return }
    $rights = @{
        SeDenyInteractiveLogonRight = @($Config.SidsNegacaoLogonLocal)
        SeDenyRemoteInteractiveLogonRight = @($Config.SidsNegacaoLogonRemoto)
    }
    $suffix = [guid]::NewGuid().ToString("N")
    $cfg = Join-Path $env:TEMP "wmt-rights-remove-$suffix.inf"
    $db = Join-Path $env:TEMP "wmt-rights-remove-$suffix.sdb"
    secedit.exe /export /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    $lines = @(Get-Content $cfg -Encoding Unicode)
    foreach ($right in $rights.Keys) {
        for ($index = 0; $index -lt $lines.Count; $index++) {
            if ($lines[$index] -notlike "$right*") { continue }
            $current = @(($lines[$index] -split "=", 2)[1] -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            $remove = @($rights[$right] | ForEach-Object { "*$($_.TrimStart('*'))" })
            $lines[$index] = "$right = $(@($current | Where-Object { $_ -notin $remove }) -join ',')"
            break
        }
    }
    Set-Content $cfg -Value $lines -Encoding Unicode
    secedit.exe /configure /db $db /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
    Remove-Item $cfg, $db -Force -ErrorAction SilentlyContinue
}

Remove-WmtDenyRights -Config $Config
if ($Config -and $Config.LockScreenBackup) {
    $backup = $Config.LockScreenBackup
    Set-WmtRegistryState $PolicyKey "LockScreenImage" $backup.PolicyImage
    Set-WmtRegistryState $PolicyKey "NoChangingLockScreen" $backup.PolicyNoChange
    Set-WmtRegistryState $CspKey "LockScreenImagePath" $backup.CspPath
    Set-WmtRegistryState $CspKey "LockScreenImageUrl" $backup.CspUrl
    Set-WmtRegistryState $CspKey "LockScreenImageStatus" $backup.CspStatus
}
# O LockApp mantém a imagem atual em memória mesmo depois da restauração
# das políticas. Encerrá-lo força o Windows a recriar a tela com a imagem
# restaurada, sem reiniciar a estação.
Get-Process LockApp -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Remove-Item (Join-Path $BasePath "ativo.flag") -Force -ErrorAction SilentlyContinue
Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object TaskName -like "TI - Modo Manutencao*" |
    Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object CommandLine -like "*TelaManutencao.ps1*" |
    ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null }
Remove-Item "HKLM:\SOFTWARE\TI\ModoManutencao" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $BasePath -Recurse -Force -ErrorAction SilentlyContinue
'@

$result = switch ($Action) {
    "status" {
        Invoke-TargetCommand -ScriptBlock {
            $basePath = "C:\ProgramData\TI\ModoManutencao"
            $config = $null
            $configPath = Join-Path $basePath "config.json"
            try {
                if (Test-Path $configPath) { $config = Get-Content $configPath -Raw -ErrorAction Stop | ConvertFrom-Json }
            } catch {}
            $flagExists = Test-Path (Join-Path $basePath "ativo.flag")
            $configuredProtection = $config -and (
                [bool]$config.LockScreenAplicada -or
                [bool]$config.BloqueioLogonLocalAplicado -or
                [bool]$config.BloqueioLogonRemotoAplicado
            )
            [pscustomobject]@{
                active = [bool]($flagExists -or $configuredProtection)
                flag_exists = $flagExists
                cleanup_required = [bool](-not $flagExists -and $configuredProtection)
                technician = if ($config) { [string]$config.NomeTecnico } else { "" }
                contact = if ($config) { [string]$config.Ramal } else { "" }
                ticket = if ($config) { [string]$config.Chamado } else { "" }
                reason = if ($config) { [string]$config.Motivo } else { "" }
                expires_at = if ($config) { [string]$config.ExpiraEm } else { "" }
                protected_users = if ($config) { @($config.UsuariosProtegidos) } else { @() }
                logon_blocked = if ($config) { [bool]$config.BloqueioLogonLocalAplicado } else { $false }
                remote_logon_blocked = if ($config) { [bool]$config.BloqueioLogonRemotoAplicado } else { $false }
                lock_screen_applied = if ($config) { [bool]$config.LockScreenAplicada } else { $false }
                mode = "lock-screen"
            }
        }
    }

    "enable" {
        Invoke-TargetCommand -ArgumentList @(
            $cleanupScript, $Technician, $TechnicianUsername, $Contact,
            $Ticket, $Reason, $DurationMinutes, $TargetUser
        ) -ScriptBlock {
            param($cleanupScript, $technician, $technicianUsername, $contact, $ticket, $reason, $durationMinutes, $targetUser)

            $basePath = "C:\ProgramData\TI\ModoManutencao"
            $configPath = Join-Path $basePath "config.json"
            $flagPath = Join-Path $basePath "ativo.flag"
            $imagePath = Join-Path $basePath ("lockscreen-{0}.png" -f [guid]::NewGuid().ToString("N"))
            $cleanupPath = Join-Path $basePath "RemoverManutencao.ps1"
            $policyKey = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization"
            $cspKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
            $expiresAt = (Get-Date).AddMinutes($durationMinutes)
            $existingConfig = $null
            try {
                if (Test-Path $configPath) { $existingConfig = Get-Content $configPath -Raw -ErrorAction Stop | ConvertFrom-Json }
            } catch {}

            function Get-WmtRegistryState {
                param([string]$Path, [string]$Name)
                $item = Get-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
                if (-not $item) { return @{ Exists = $false; Value = ""; Kind = "String" } }
                $kind = (Get-Item $Path).GetValueKind($Name).ToString()
                return @{ Exists = $true; Value = $item.$Name; Kind = $kind }
            }

            function Add-WmtDenyRights {
                param([string[]]$Users)
                $sids = @(
                    foreach ($userName in $Users) {
                        $account = if ($userName -match "\\") { $userName } else { "$env:USERDOMAIN\$userName" }
                        try {
                            ([System.Security.Principal.NTAccount]$account).
                                Translate([System.Security.Principal.SecurityIdentifier]).Value
                        } catch {}
                    }
                ) | Sort-Object -Unique
                $added = @{
                    SeDenyInteractiveLogonRight = @()
                    SeDenyRemoteInteractiveLogonRight = @()
                    ResolvedSids = @($sids)
                }
                if (-not $sids.Count) { return $added }
                $suffix = [guid]::NewGuid().ToString("N")
                $cfg = Join-Path $env:TEMP "wmt-rights-add-$suffix.inf"
                $db = Join-Path $env:TEMP "wmt-rights-add-$suffix.sdb"
                secedit.exe /export /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Falha ao exportar direitos locais. Código: $LASTEXITCODE" }
                $lines = [System.Collections.ArrayList]@(Get-Content $cfg -Encoding Unicode)
                foreach ($right in @("SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight")) {
                    $index = -1
                    for ($i = 0; $i -lt $lines.Count; $i++) {
                        if ($lines[$i] -like "$right*") { $index = $i; break }
                    }
                    $current = New-Object System.Collections.Generic.List[string]
                    if ($index -ge 0) {
                        @(($lines[$index] -split "=", 2)[1] -split "," |
                            ForEach-Object { $_.Trim() } |
                            Where-Object { $_ }) |
                            ForEach-Object { $current.Add([string]$_) }
                    }
                    foreach ($sid in $sids) {
                        $entry = "*$sid"
                        if ($entry -notin $current) {
                            $current.Add($entry)
                            $added[$right] += $sid
                        }
                    }
                    $line = "$right = $($current -join ',')"
                    if ($index -ge 0) { $lines[$index] = $line } else { [void]$lines.Add($line) }
                }
                Set-Content $cfg -Value $lines -Encoding Unicode
                secedit.exe /configure /db $db /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Falha ao aplicar bloqueio de logon. Código: $LASTEXITCODE" }
                Remove-Item $cfg, $db -Force -ErrorAction SilentlyContinue
                return $added
            }

            function New-WmtLockScreen {
                param(
                    [string]$Path, [string]$Ticket, [string]$Reason,
                    [string]$Technician, [string]$Contact, [datetime]$ExpiresAt
                )
                Add-Type -AssemblyName System.Drawing
                $bitmap = New-Object System.Drawing.Bitmap 1920, 1080
                $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                $graphics.SmoothingMode = "AntiAlias"
                $graphics.TextRenderingHint = "AntiAliasGridFit"
                $graphics.Clear([System.Drawing.Color]::FromArgb(10, 18, 26))

                $yellow = [System.Drawing.Color]::FromArgb(255, 204, 0)
                $white = [System.Drawing.Color]::White
                $soft = [System.Drawing.Color]::FromArgb(225, 229, 233)
                $muted = [System.Drawing.Color]::FromArgb(170, 178, 186)
                $center = New-Object System.Drawing.StringFormat
                $center.Alignment = "Center"
                $center.LineAlignment = "Center"
                $wrap = New-Object System.Drawing.StringFormat
                $wrap.Alignment = "Center"
                $wrap.LineAlignment = "Near"

                $titleFont = New-Object System.Drawing.Font "Segoe UI", 48, ([System.Drawing.FontStyle]::Bold)
                $bodyFont = New-Object System.Drawing.Font "Segoe UI", 20
                $detailFont = New-Object System.Drawing.Font "Segoe UI", 18
                $smallFont = New-Object System.Drawing.Font "Segoe UI", 14
                $yellowBrush = New-Object System.Drawing.SolidBrush $yellow
                $whiteBrush = New-Object System.Drawing.SolidBrush $white
                $softBrush = New-Object System.Drawing.SolidBrush $soft
                $mutedBrush = New-Object System.Drawing.SolidBrush $muted
                $darkPanelBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(235, 18, 30, 42))
                $titleDarkBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(16, 24, 32))

                # Faixa superior permanece visível mesmo com os elementos de
                # data/hora e autenticação desenhados pelo Windows.
                $graphics.FillRectangle($yellowBrush, 0, 0, 1920, 155)
                $graphics.DrawString("COMPUTADOR EM MANUTENÇÃO", $titleFont, $titleDarkBrush, (New-Object System.Drawing.RectangleF 120, 25, 1680, 100), $center)

                # Painel à direita evita a região normalmente usada pelo relógio
                # e pela data na lock screen do Windows.
                $graphics.FillRectangle($darkPanelBrush, 1010, 205, 820, 815)
                $graphics.DrawString("ACESSO TEMPORARIAMENTE INDISPONÍVEL", $bodyFont, $yellowBrush, (New-Object System.Drawing.RectangleF 1060, 245, 720, 65), $center)
                $graphics.DrawString("Este computador está sendo acessado remotamente pelo Departamento de Tecnologia da Informação.`n`nNão utilize, desligue ou reinicie o equipamento até a conclusão do atendimento.", $bodyFont, $softBrush, (New-Object System.Drawing.RectangleF 1060, 340, 720, 210), $wrap)
                $safeReason = if ($Reason.Length -gt 120) { $Reason.Substring(0, 117) + "..." } else { $Reason }
                $graphics.DrawString("Chamado: $Ticket`nMotivo: $safeReason", $detailFont, $whiteBrush, (New-Object System.Drawing.RectangleF 1060, 585, 720, 135), $wrap)
                $release = $ExpiresAt.ToString("dd/MM/yyyy HH:mm")
                $graphics.DrawString("Técnico responsável: $Technician`nContato: $Contact`nPrevisão de liberação: $release", $detailFont, $yellowBrush, (New-Object System.Drawing.RectangleF 1060, 750, 720, 145), $wrap)
                $graphics.DrawString("O acesso permanecerá indisponível enquanto a manutenção estiver ativa.", $smallFont, $mutedBrush, (New-Object System.Drawing.RectangleF 1050, 940, 740, 45), $center)

                $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
                $graphics.Dispose()
                $bitmap.Dispose()
                @($titleFont, $bodyFont, $detailFont, $smallFont, $yellowBrush, $whiteBrush, $softBrush, $mutedBrush, $darkPanelBrush, $titleDarkBrush, $center, $wrap) |
                    ForEach-Object { $_.Dispose() }
            }

            $supportLogin = ($technicianUsername -split "\\")[-1]
            $sessions = @(
                quser.exe 2>$null | Select-Object -Skip 1 | ForEach-Object {
                    if ($_ -match "^\s*>?(\S+)\s+(?:\S+\s+)?(\d+)\s+") {
                        [pscustomobject]@{ User = $matches[1]; Id = [int]$matches[2] }
                    }
                }
            )
            $protectedUsers = @(
                @($sessions.User) + @(if ($targetUser) { ($targetUser -split "\\")[-1] })
            ) | Where-Object { $_ -and $_ -ne $supportLogin } | Sort-Object -Unique

            New-Item $basePath -ItemType Directory -Force | Out-Null
            Get-ScheduledTask -ErrorAction SilentlyContinue |
                Where-Object TaskName -like "TI - Modo Manutencao*" |
                Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
            Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
                Where-Object CommandLine -like "*TelaManutencao.ps1*" |
                ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null }
            Remove-Item (Join-Path $basePath "TelaManutencao.ps1") -Force -ErrorAction SilentlyContinue

            $backup = if ($existingConfig -and $existingConfig.LockScreenBackup) {
                $existingConfig.LockScreenBackup
            } else {
                @{
                    PolicyImage = Get-WmtRegistryState $policyKey "LockScreenImage"
                    PolicyNoChange = Get-WmtRegistryState $policyKey "NoChangingLockScreen"
                    CspPath = Get-WmtRegistryState $cspKey "LockScreenImagePath"
                    CspUrl = Get-WmtRegistryState $cspKey "LockScreenImageUrl"
                    CspStatus = Get-WmtRegistryState $cspKey "LockScreenImageStatus"
                }
            }
            New-WmtLockScreen $imagePath $ticket $reason $technician $contact $expiresAt
            $addedRights = Add-WmtDenyRights -Users $protectedUsers

            New-Item $policyKey -Force | Out-Null
            New-ItemProperty $policyKey -Name "LockScreenImage" -PropertyType String -Value $imagePath -Force | Out-Null
            New-ItemProperty $policyKey -Name "NoChangingLockScreen" -PropertyType DWord -Value 1 -Force | Out-Null
            New-Item $cspKey -Force | Out-Null
            New-ItemProperty $cspKey -Name "LockScreenImagePath" -PropertyType String -Value $imagePath -Force | Out-Null
            New-ItemProperty $cspKey -Name "LockScreenImageUrl" -PropertyType String -Value $imagePath -Force | Out-Null
            New-ItemProperty $cspKey -Name "LockScreenImageStatus" -PropertyType DWord -Value 1 -Force | Out-Null
            Get-Process LockApp -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

            Set-Content $cleanupPath -Value $cleanupScript -Encoding UTF8 -Force
            @{
                NomeTecnico = $technician
                Ramal = $contact
                Chamado = $ticket
                Motivo = $reason
                ExpiraEm = $expiresAt.ToUniversalTime().ToString("o")
                UsuariosProtegidos = $protectedUsers
                SidsNegacaoLogonLocal = @(@($existingConfig.SidsNegacaoLogonLocal) + @($addedRights.SeDenyInteractiveLogonRight) | Sort-Object -Unique)
                SidsNegacaoLogonRemoto = @(@($existingConfig.SidsNegacaoLogonRemoto) + @($addedRights.SeDenyRemoteInteractiveLogonRight) | Sort-Object -Unique)
                BloqueioLogonLocalAplicado = @($addedRights.ResolvedSids).Count -gt 0
                BloqueioLogonRemotoAplicado = @($addedRights.ResolvedSids).Count -gt 0
                LockScreenAplicada = $true
                LockScreenImage = $imagePath
                LockScreenBackup = $backup
            } | ConvertTo-Json -Depth 8 | Set-Content $configPath -Encoding UTF8 -Force
            Set-Content $flagPath -Value "ATIVO" -Encoding ASCII -Force

            $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            $expiryAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$cleanupPath`""
            $expiryTrigger = New-ScheduledTaskTrigger -Once -At $expiresAt
            $expiryPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            Register-ScheduledTask -TaskName "TI - Modo Manutencao - Expiracao" -Action $expiryAction -Trigger $expiryTrigger -Principal $expiryPrincipal -Settings $settings -Description "Remoção automática do modo manutenção" -Force | Out-Null

            foreach ($session in $sessions | Where-Object { $_.User -in $protectedUsers }) {
                tsdiscon.exe $session.Id 2>$null
            }

            [pscustomobject]@{
                active = $true
                technician = $technician
                contact = $contact
                ticket = $ticket
                reason = $reason
                expires_at = $expiresAt.ToUniversalTime().ToString("o")
                protected_users = $protectedUsers
                logon_blocked = @($addedRights.ResolvedSids).Count -gt 0
                remote_logon_blocked = @($addedRights.ResolvedSids).Count -gt 0
                lock_screen_applied = $true
                mode = "lock-screen"
            }
        }
    }

    "disable" {
        Invoke-TargetCommand -ArgumentList @($cleanupScript) -ScriptBlock {
            param($currentCleanupScript)
            $basePath = "C:\ProgramData\TI\ModoManutencao"
            $cleanupPath = Join-Path $basePath "RemoverManutencao.ps1"
            if (Test-Path $basePath) {
                Set-Content $cleanupPath -Value $currentCleanupScript -Encoding UTF8 -Force
                & $cleanupPath
            } else {
                Remove-Item (Join-Path $basePath "ativo.flag") -Force -ErrorAction SilentlyContinue
                Get-ScheduledTask -ErrorAction SilentlyContinue |
                    Where-Object TaskName -like "TI - Modo Manutencao*" |
                    Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
                Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
                    Where-Object CommandLine -like "*TelaManutencao.ps1*" |
                    ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null }
                Remove-Item $basePath -Recurse -Force -ErrorAction SilentlyContinue
            }
            [pscustomobject]@{
                active = $false
                technician = ""
                contact = ""
                ticket = ""
                reason = ""
                expires_at = ""
                protected_users = @()
                logon_blocked = $false
                remote_logon_blocked = $false
                lock_screen_applied = $false
                mode = "lock-screen"
            }
        }
    }
}

$result | Select-Object -First 1 | ConvertTo-Json -Compress -Depth 6
