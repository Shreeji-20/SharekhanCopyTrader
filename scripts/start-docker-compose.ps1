[CmdletBinding()]
param(
    [string]$ProjectDirectory = (Split-Path -Parent $PSScriptRoot),
    [ValidateRange(30, 900)]
    [int]$DockerStartupTimeoutSeconds = 180,
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = (Resolve-Path -LiteralPath $ProjectDirectory).Path
$ComposeFile = Join-Path $ProjectDirectory "docker-compose.yml"

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "docker-compose.yml was not found in $ProjectDirectory"
}

if (-not $LogPath) {
    $LogPath = Join-Path $ProjectDirectory "logs\docker-autostart.log"
}

$LogDirectory = Split-Path -Parent $LogPath
if ($LogDirectory) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
}

function Write-StartupLog {
    param([string]$Message)

    $Line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogPath -Value $Line
    Write-Output $Line
}

function Resolve-DockerExecutable {
    $Command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $Candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\resources\bin\docker.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

    if ($Candidates.Count -eq 0) {
        throw "Docker CLI was not found. Install Docker Desktop before enabling project auto-start."
    }

    return $Candidates[0]
}

function Test-DockerEngine {
    param([string]$DockerExecutable)

    try {
        & $DockerExecutable info --format "{{.ServerVersion}}" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Start-DockerDesktopIfNeeded {
    param([string]$DockerExecutable)

    if (Test-DockerEngine -DockerExecutable $DockerExecutable) {
        return
    }

    $DesktopCandidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        if ($DesktopCandidates.Count -eq 0) {
            throw "Docker Desktop was not found. Enable Docker Desktop startup manually or reinstall it."
        }

        Write-StartupLog "Starting Docker Desktop."
        Start-Process -FilePath $DesktopCandidates[0] -WindowStyle Hidden
    }

    $Deadline = (Get-Date).AddSeconds($DockerStartupTimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine -DockerExecutable $DockerExecutable) {
            Write-StartupLog "Docker engine is ready."
            return
        }
    }

    throw "Docker engine was not ready after $DockerStartupTimeoutSeconds seconds."
}

try {
    Write-StartupLog "Starting Sharekhan Copy Trader containers from $ProjectDirectory."
    $DockerExecutable = Resolve-DockerExecutable
    Start-DockerDesktopIfNeeded -DockerExecutable $DockerExecutable

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $ComposeOutput = & $DockerExecutable compose --project-directory $ProjectDirectory -f $ComposeFile up -d 2>&1
        $ComposeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    foreach ($Line in $ComposeOutput) {
        Write-StartupLog ([string]$Line)
    }

    if ($ComposeExitCode -ne 0) {
        throw "docker compose up -d exited with code $ComposeExitCode."
    }

    Write-StartupLog "Sharekhan Copy Trader containers are running."
}
catch {
    Write-StartupLog "Auto-start failed: $($_.Exception.Message)"
    throw
}
