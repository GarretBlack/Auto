$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

if (-not (Test-Path ".\.venv")) {
    python -m venv .venv
}

if (-not (Test-Path ".\logs")) {
    New-Item -ItemType Directory -Path ".\logs" | Out-Null
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r ".\requirements.txt"

Write-Host 'Environment ready. Config: .\config.json, logs: .\logs, activate: .\.venv\Scripts\Activate.ps1'
