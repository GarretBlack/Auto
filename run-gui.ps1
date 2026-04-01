$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Виртуальное окружение не найдено. Сначала выполните .\setup.ps1"
    exit 1
}

& ".\.venv\Scripts\python.exe" ".\gui.py"
