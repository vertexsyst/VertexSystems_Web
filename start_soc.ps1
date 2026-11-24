$ErrorActionPreference = "Stop"
Set-Location "V:\Development\VertexSystems_Web"

if (-not (Test-Path ".env")) {
    Write-Warning ".env file is missing! Entra ID and SQL credentials may fail to load."
}

$existing = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

& ".\.venv\Scripts\python.exe" "app.py"
