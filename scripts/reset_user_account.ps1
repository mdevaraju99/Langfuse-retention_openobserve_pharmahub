<#
PowerShell helper to run the Python `reset_user_account.py` script without sharing credentials.

Usage: run this in the repo root PowerShell prompt:
  powershell -ExecutionPolicy Bypass -File .\scripts\reset_user_account.ps1

The script will:
 - Prompt for DB host, port, user, database and password (password entered securely and not printed)
 - Optionally run a pg_dump backup (if pg_dump is on PATH)
 - Ensure Python deps are installed (psycopg2-binary, passlib[bcrypt])
 - Run the Python script in --dry-run mode and show output
 - Ask for confirmation and run the real change if you accept

This keeps credentials on your machine only.
#>

function Read-Secret([string]$prompt) {
    $secure = Read-Host -AsSecureString -Prompt $prompt
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) } finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

Write-Host "This helper will run scripts/reset_user_account.py locally. Credentials will NOT be sent anywhere."

$hostName = Read-Host "DB host or IP (e.g. localhost)"
$port = Read-Host "DB port (default 5432)"; if (-not $port) { $port = 5432 }
$dbUser = Read-Host "DB user"
$dbName = Read-Host "DB name"
$dbPass = Read-Secret "DB password (input hidden)"

# percent-encode the password for URL
$encPass = [System.Uri]::EscapeDataString($dbPass)

$dsn = "postgres://$($dbUser):$($encPass)@$($hostName):$($port)/$($dbName)"

Write-Host "Constructed DSN host:" $hostName

Write-Host "Would you like to create a pg_dump backup first? (y/N)"
$doBackup = Read-Host
if ($doBackup -match '^[Yy]') {
    if (Get-Command pg_dump -ErrorAction SilentlyContinue) {
        $timestamp = Get-Date -Format yyyyMMddHHmmss
        $outFile = "db-backup-$timestamp.dump"
        Write-Host "Running pg_dump to $outFile ..."
        # set PGPASSWORD only in this process
        $env:PGPASSWORD = $dbPass
        & pg_dump -h $hostName -p $port -U $dbUser -Fc -f $outFile $dbName
        Remove-Item Env:PGPASSWORD
        Write-Host "pg_dump finished. Backup file: $outFile"
    } else {
        Write-Host "pg_dump not found on PATH; skipping backup. You can install PostgreSQL client tools or back up using another method."
    }
}

Write-Host "Ensuring Python dependencies are installed (psycopg2-binary, passlib[bcrypt])"
& python -m pip install --upgrade pip | Out-Null
& python -m pip install psycopg2-binary passlib[bcrypt]

Write-Host "Running Python script in --dry-run mode (no DB changes)..."
$env:DATABASE_URL = $dsn
$oldEmail = Read-Host "Old email to modify"
$newPassword = Read-Host "New password to set (will be shown while typing)"
# Use single quotes around arguments to preserve special characters
& python .\scripts\reset_user_account.py --old-email "$oldEmail" --set-password "$newPassword" --dry-run

Write-Host "Dry-run complete. If the output looked correct, type 'apply' to commit the change, or anything else to abort." -ForegroundColor Yellow
$confirm = Read-Host
if ($confirm -eq 'apply') {
    Write-Host "Applying change now..."
    & python .\scripts\reset_user_account.py --old-email "$oldEmail" --set-password "$newPassword" --hash-method bcrypt --yes
    Write-Host "Operation finished. Remove any temporary files and clear credentials from your shell if needed." -ForegroundColor Green
} else {
    Write-Host "Aborted. No changes applied." -ForegroundColor Cyan
}
