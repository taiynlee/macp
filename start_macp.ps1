# MACP Quick Start — Windows
# Double-click or run from PowerShell to start Backend + Frontend after reboot.

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Starting MACP..." -ForegroundColor Cyan
Write-Host ""

# ── Backend ───────────────────────────────────────────────────────────────────
Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", "
  `$host.UI.RawUI.WindowTitle = 'MACP Backend';
  Set-Location '$Root\backend';
  .\.venv\Scripts\Activate.ps1;
  Write-Host '=== MACP Backend (port 8010) ===' -ForegroundColor Cyan;
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
"

Start-Sleep -Seconds 2

# ── Frontend ──────────────────────────────────────────────────────────────────
Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", "
  `$host.UI.RawUI.WindowTitle = 'MACP Frontend';
  Set-Location '$Root\frontend';
  Write-Host '=== MACP Frontend (port 5173) ===' -ForegroundColor Green;
  npm run dev
"

# ── Open browser when ready ───────────────────────────────────────────────────
Start-Sleep -Seconds 7
Start-Process "http://localhost:5173"

Write-Host "  Backend  -> http://localhost:8010" -ForegroundColor Yellow
Write-Host "  Frontend -> http://localhost:5173" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Next: start dba_agent in WSL, then agents on remote Ubuntu." -ForegroundColor DarkGray
Write-Host ""
