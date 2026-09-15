# Local launcher for Izolyat (SQLite, no Supabase).
#
#   .\start-local.ps1            start
#   .\start-local.ps1 -Fresh     recreate the local database and demo data
#   .\start-local.ps1 -Lan       serve on the LAN so phones can open the survey
#   .\start-local.ps1 -Port 8080 use another port
#
# NOTE: messages here are intentionally ASCII-only. The Windows console is not
# UTF-8 by default, and Cyrillic text printed from a .ps1 turns into mojibake.
# The app itself is fully Russian - this is only the launcher's own output.
#
# The script does NOT touch .env: the production Supabase connection stays
# untouched, everything goes into a local izolyat.db next to the project.

param(
    [switch]$Fresh,
    [switch]$Lan,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Interpreter: prefer the one that has the dependencies installed.
$py = "C:\Python314\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# Environment variables override .env, so Supabase is not used.
$env:DATABASE_URL = "sqlite:///izolyat.db"
$env:SECRET_KEY = "local-dev-secret-not-for-production"
$env:REGISTRATION_INVITE_CODE = ""

# Russian output (seed messages) needs the console and Python to agree on the
# encoding. We switch the console to UTF-8 and tell Python to use it too;
# without this pair the demo credentials print as garbage on Windows.
try { chcp 65001 > $null } catch {}
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = "utf-8"

$dbPath = Join-Path $PSScriptRoot "izolyat.db"
$needSeed = $Fresh -or -not (Test-Path $dbPath)

if ($Fresh -and (Test-Path $dbPath)) {
    Write-Host "Removing old local database..." -ForegroundColor Yellow
    Remove-Item -LiteralPath $dbPath -Force
}

Write-Host "Applying migrations..." -ForegroundColor Cyan
& $py -m alembic upgrade head

if ($needSeed) {
    Write-Host "Seeding demo data..." -ForegroundColor Cyan
    & $py -m app.seed
}

Write-Host ""
Write-Host "  Login (psychologist + admin): demo@izolyat.local / demo12345" -ForegroundColor Green
Write-Host "  Login (head teacher):         zavuch@izolyat.local / demo12345" -ForegroundColor Green
Write-Host ""

$runArgs = @("run.py", "--port", $Port, "--no-reload")
if ($Lan) { $runArgs += "--lan" }
& $py @runArgs
