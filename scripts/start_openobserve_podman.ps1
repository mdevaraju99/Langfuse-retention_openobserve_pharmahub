<#
.SYNOPSIS
  Start Podman (Windows VM) and run OpenObserve for this Pharma POC.

.DESCRIPTION
  - Ensures Podman CLI exists and the VM is reachable
  - Creates/starts container "openobserve" on localhost:5080
  - Persists data in podman volume openobserve-data

.EXAMPLE
  .\scripts\start_openobserve_podman.ps1

.EXAMPLE
  .\scripts\start_openobserve_podman.ps1 -RootEmail "admin@example.com" -RootPassword "Password@123"
#>
param(
    [string]$MachineName = "neo4j-machine",
    [string]$ContainerName = "openobserve",
    [string]$Image = "public.ecr.aws/zinclabs/openobserve:latest",
    [string]$RootEmail = "admin@example.com",
    [string]$RootPassword = "Password@123",
    [int]$Port = 5080,
    [string]$VolumeName = "openobserve-data",
    [switch]$SkipTlsVerify
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Podman {
    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        throw "Podman CLI is not installed or not on PATH."
    }
}

function Test-PodmanConnection {
    podman info --format "{{.Host.Arch}}" 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Ensure-Machine {
    param([string]$Name)

    $machineExists = $false
    $listOutput = podman machine list --format "{{.Name}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $listOutput) {
        $machineExists = ($listOutput -split "`n" | ForEach-Object { $_.Trim() }) -contains $Name
    }

    if (-not $machineExists) {
        Write-Step "Creating podman machine '$Name' with user-mode networking"
        podman machine init --user-mode-networking --cpus 2 --memory 4096 --disk-size 30 $Name
    }

    Write-Step "Starting podman machine '$Name'"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        podman machine start $Name 2>&1 | Out-Null
    } finally {
        $ErrorActionPreference = $prevEap
    }

    if (-not (Test-PodmanConnection)) {
        Write-Step "Podman socket stale. Restarting '$Name'..."
        podman machine stop $Name 2>&1 | Out-Null
        Start-Sleep -Seconds 3
        podman machine start $Name 2>&1 | Out-Null
        if (-not (Test-PodmanConnection)) {
            throw "Podman still unreachable. Try: wsl --shutdown, then re-run this script."
        }
    }
}

function Ensure-RootConnection {
    param([string]$Name)

    $rootConn = "$Name-root"
    Write-Step "Setting default podman connection to '$rootConn'"
    podman system connection default $rootConn
}

function Ensure-Volume {
    param([string]$Name)

    $exists = podman volume exists $Name 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Creating volume '$Name'"
        podman volume create $Name | Out-Null
    }
}

function Start-OpenObserveContainer {
    param(
        [string]$Name,
        [string]$ImageName,
        [string]$Email,
        [string]$Password,
        [int]$HostPort,
        [string]$Volume
    )

    $running = $false
    $inspect = podman ps -a --filter "name=^$Name$" --format "{{.Names}}|{{.Status}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $inspect) {
        if ($inspect -match "Up") {
            $running = $true
        }
    }

    if ($running) {
        Write-Step "Container '$Name' already running"
        return
    }

    if ($inspect) {
        Write-Step "Starting existing container '$Name'"
        podman start $Name | Out-Null
        return
    }

    Write-Step "Creating and starting container '$Name'"
    # Corporate TLS interception often breaks registry pulls; skip verify for bootstrap.
    podman pull --tls-verify=false $ImageName 2>&1 | Out-Null
    podman run -d `
        --name $Name `
        -p "127.0.0.1:${HostPort}:5080" `
        -v "${Volume}:/data" `
        -e ZO_DATA_DIR="/data" `
        -e ZO_ROOT_USER_EMAIL="$Email" `
        -e ZO_ROOT_USER_PASSWORD="$Password" `
        $ImageName | Out-Null
}

function Verify-Endpoint {
    param([int]$HostPort)

    Write-Step "Verifying OpenObserve UI on http://127.0.0.1:$HostPort"
    Start-Sleep -Seconds 10

    try {
        $resp = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 5 "http://127.0.0.1:$HostPort/web/" -TimeoutSec 20
        $httpStatus = $resp.StatusCode
    } catch {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$HostPort/healthz" -TimeoutSec 10
            $httpStatus = $resp.StatusCode
        } catch {
            $httpStatus = "unreachable (container may still be starting - check: podman logs openobserve)"
        }
    }

    Write-Host "HTTP 127.0.0.1:$HostPort -> $httpStatus"
}

function Get-BasicAuthToken {
    param([string]$Email, [string]$Password)

    $pair = "$Email`:$Password"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($pair)
    return [Convert]::ToBase64String($bytes)
}

Write-Step "Podman OpenObserve bootstrap for Pharma POC"
Ensure-Podman
Ensure-Machine -Name $MachineName
Ensure-RootConnection -Name $MachineName
Ensure-Volume -Name $VolumeName
Start-OpenObserveContainer -Name $ContainerName -ImageName $Image -Email $RootEmail -Password $RootPassword -HostPort $Port -Volume $VolumeName
Verify-Endpoint -HostPort $Port

$token = Get-BasicAuthToken -Email $RootEmail -Password $RootPassword

Write-Host ""
Write-Host "Done. Add these to your .env:" -ForegroundColor Green
Write-Host "ENABLE_OPENOBSERVE=true"
Write-Host "OPENOBSERVE_URL=http://localhost:5080"
Write-Host "OPENOBSERVE_ORG=default"
Write-Host "OPENOBSERVE_AUTH_TOKEN=Basic $token"
Write-Host "OPENOBSERVE_SERVICE_NAME=pharma-hub"
Write-Host "OPENOBSERVE_STREAM=default"
Write-Host ""
Write-Host "OpenObserve UI: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Login: $RootEmail / $RootPassword"
