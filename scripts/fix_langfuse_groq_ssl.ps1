# Fix Langfuse LLM-as-a-Judge "Connection error" / "Request timed out" on corporate networks.
# Cause: Cisco Umbrella (or similar) intercepts HTTPS; Langfuse containers don't trust the corporate CA.
#
# Prerequisites: Langfuse running via podman compose in $LangfuseDir (default C:\Users\mdevaraju\langfuse)
# Run from Pharma project root:
#   .\scripts\fix_langfuse_groq_ssl.ps1

$ErrorActionPreference = "Stop"

$LangfuseDir = if ($env:LANGFUSE_DIR) { $env:LANGFUSE_DIR } else { "C:\Users\mdevaraju\langfuse" }
$CertDir = Join-Path $LangfuseDir "certs"
$CertFile = Join-Path $CertDir "cisco-umbrella-root.pem"
$ComposeFile = Join-Path $LangfuseDir "docker-compose.yml"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Write-Step "Export Cisco Umbrella root CA (if present in Windows trust store)"
New-Item -ItemType Directory -Force -Path $CertDir | Out-Null
$cert = Get-ChildItem -Path Cert:\LocalMachine\Root, Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -like "*Umbrella Root*" -or $_.Subject -like "*Cisco Umbrella Root*" } |
    Select-Object -First 1
if (-not $cert) {
    Write-Host "No Cisco Umbrella root CA found. Export your corporate root CA manually to:" -ForegroundColor Yellow
    Write-Host "  $CertFile"
    exit 1
}
$b64 = [Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks')
$pem = "-----BEGIN CERTIFICATE-----`n$b64`n-----END CERTIFICATE-----`n"
Set-Content -Path $CertFile -Value $pem -Encoding ascii -NoNewline
Write-Host "Wrote $CertFile ($($cert.Subject))"

Write-Step "Check docker-compose.yml has NODE_EXTRA_CA_CERTS + cert volume"
if (-not (Test-Path $ComposeFile)) {
    Write-Host "Missing $ComposeFile" -ForegroundColor Red
    exit 1
}
$composeText = Get-Content $ComposeFile -Raw
if ($composeText -notmatch "NODE_EXTRA_CA_CERTS") {
    Write-Host @"
docker-compose.yml is not patched yet. Add to langfuse-worker AND langfuse-web:

  environment:
    NODE_EXTRA_CA_CERTS: /langfuse-certs/ca.pem
  volumes:
    - ./certs/cisco-umbrella-root.pem:/langfuse-certs/ca.pem:ro

See scripts/fix_langfuse_groq_ssl.ps1 header or ops/README.md
"@ -ForegroundColor Yellow
    exit 1
}
Write-Host "docker-compose.yml already references NODE_EXTRA_CA_CERTS"

Write-Step "Recreate Langfuse worker + web"
Push-Location $LangfuseDir
try {
    podman compose up -d langfuse-worker langfuse-web
} finally {
    Pop-Location
}

Write-Step "Test Groq HTTPS from langfuse-worker (expect STATUS 200 or 401, not UNABLE_TO_GET_ISSUER_CERT)"
$worker = (podman ps --format "{{.Names}}" | Select-String "langfuse-worker" | Select-Object -First 1).ToString().Trim()
if (-not $worker) {
    Write-Host "langfuse-worker container not running" -ForegroundColor Red
    exit 1
}
$test = podman exec $worker node -e 'fetch("https://api.groq.com/openai/v1/models").then(r=>console.log("STATUS",r.status)).catch(e=>console.log("ERROR",e.cause&&e.cause.code||e.message))'
Write-Host $test
if ($test -match 'UNABLE_TO_GET_ISSUER|fetch failed|ERROR') {
    Write-Host 'Groq still unreachable from container - check proxy/CA.' -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host 'Done. In Langfuse UI:' -ForegroundColor Green
Write-Host '  1. Settings - LLM Connections - Groq judge - Save (should succeed now)'
Write-Host '  2. Evaluation - LLM-as-a-Judge - new Company Knowledge question - Logs should show Completed'
Write-Host '  3. Turn off duplicate Active evaluators (keep one Toxicity, one Helpfulness)'
