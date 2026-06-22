[CmdletBinding()]
param(
    [string]$TaskName = "SharekhanCopyTrader-Docker-Autostart",
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$Runner = Join-Path $PSScriptRoot "start-docker-compose.ps1"

if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) {
    throw "Auto-start runner was not found at $Runner"
}

$PowerShellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`" -ProjectDirectory `"$ProjectDirectory`""

$Action = New-ScheduledTaskAction `
    -Execute $PowerShellExecutable `
    -Argument $Arguments `
    -WorkingDirectory $ProjectDirectory
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Start Docker Desktop and the Sharekhan Copy Trader Compose stack at user logon." `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Force | Out-Null

Write-Output "Installed scheduled task: $TaskName"
Write-Output "Project directory: $ProjectDirectory"
Write-Output "Startup log: $(Join-Path $ProjectDirectory 'logs\docker-autostart.log')"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Started scheduled task: $TaskName"
}
