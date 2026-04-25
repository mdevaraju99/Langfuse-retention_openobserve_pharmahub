param(
    [string]$MachineName = "neo4j-machine",
    [string]$ContainerName = "neo4j",
    [string]$Neo4jImage = "docker.io/library/neo4j:5",
    [string]$Neo4jAuth = "neo4j/password123",
    [int]$HttpPort = 7474,
    [int]$BoltPort = 7687
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
    try {
        podman machine start $Name
    } catch {
        # If already running, continue.
        $msg = $_.Exception.Message
        if ($msg -notmatch "already running") {
            throw
        }
    }
}

function Ensure-RootConnection {
    param([string]$Name)

    $rootConn = "$Name-root"
    Write-Step "Setting default podman connection to '$rootConn'"
    podman system connection default $rootConn
}

function Start-Neo4jContainer {
    param(
        [string]$Name,
        [string]$Image,
        [string]$Auth,
        [int]$PortHttp,
        [int]$PortBolt
    )

    $exists = $false
    $running = $false

    $inspect = podman ps -a --filter "name=^$Name$" --format "{{.Names}}|{{.Status}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $inspect) {
        $exists = $true
        if ($inspect -match "Up") {
            $running = $true
        }
    }

    if ($running) {
        Write-Step "Container '$Name' already running"
        return
    }

    if ($exists) {
        Write-Step "Starting existing container '$Name'"
        podman start $Name | Out-Null
        return
    }

    Write-Step "Creating and starting container '$Name'"
    podman run -d `
        --name $Name `
        -p "${PortHttp}:7474" `
        -p "${PortBolt}:7687" `
        -e "NEO4J_AUTH=$Auth" `
        $Image | Out-Null
}

function Verify-Endpoints {
    param([int]$PortHttp, [int]$PortBolt)

    Write-Step "Verifying Neo4j endpoints"

    # Allow startup time for first run.
    Start-Sleep -Seconds 8

    try {
        $httpStatus = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$PortHttp").StatusCode
    } catch {
        $httpStatus = "unreachable"
    }

    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $boltOk = $false
    try {
        $tcpClient.Connect("127.0.0.1", $PortBolt)
        $boltOk = $tcpClient.Connected
    } catch {
        $boltOk = $false
    } finally {
        $tcpClient.Close()
    }

    Write-Host "HTTP 127.0.0.1:$PortHttp -> $httpStatus"
    Write-Host "BOLT 127.0.0.1:$PortBolt -> $boltOk"
}

Write-Step "Podman Neo4j bootstrap for Pharma POC"
Ensure-Podman
Ensure-Machine -Name $MachineName
Ensure-RootConnection -Name $MachineName
Start-Neo4jContainer -Name $ContainerName -Image $Neo4jImage -Auth $Neo4jAuth -PortHttp $HttpPort -PortBolt $BoltPort
Verify-Endpoints -PortHttp $HttpPort -PortBolt $BoltPort

Write-Host ""
Write-Host "Done. Use these .env values for this POC:" -ForegroundColor Green
Write-Host "NEO4J_URI=bolt://127.0.0.1:$BoltPort"
Write-Host "NEO4J_USER=neo4j"
Write-Host "NEO4J_PASSWORD=$($Neo4jAuth.Split('/')[1])"
