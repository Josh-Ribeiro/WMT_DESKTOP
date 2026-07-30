#Requires -Version 7.0

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-CheckedStep {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

Push-Location $projectRoot
try {
    Invoke-CheckedStep "Frontend formatting" {
        & corepack pnpm format:check
    }
    Invoke-CheckedStep "Frontend typecheck" {
        & corepack pnpm check
    }
    Invoke-CheckedStep "Frontend tests" {
        & corepack pnpm test
    }
    Invoke-CheckedStep "Frontend production build" {
        & corepack pnpm build
    }
    Invoke-CheckedStep "Backend tests" {
        & python -m unittest discover -s backend/tests -v
    }
    Invoke-CheckedStep "Backend syntax" {
        & python -m compileall -q backend
    }
    Invoke-CheckedStep "Rust check" {
        Push-Location "src-tauri"
        try {
            & cargo check
        }
        finally {
            Pop-Location
        }
    }

    Write-Host ""
    Write-Host "==> PowerShell syntax" -ForegroundColor Cyan
    $parseFailures = [System.Collections.Generic.List[string]]::new()
    Get-ChildItem "scripts", "backend/scripts" -Filter "*.ps1" -Recurse |
        ForEach-Object {
            $tokens = $null
            $parseErrors = $null
            [System.Management.Automation.Language.Parser]::ParseFile(
                $_.FullName,
                [ref]$tokens,
                [ref]$parseErrors
            ) | Out-Null
            foreach ($parseError in $parseErrors) {
                $parseFailures.Add(
                    "$($parseError.Extent.File):$($parseError.Extent.StartLineNumber): $($parseError.Message)"
                )
            }
        }
    if ($parseFailures.Count -gt 0) {
        throw ($parseFailures -join [Environment]::NewLine)
    }

    Write-Host ""
    Write-Host "All WMT verification steps passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
