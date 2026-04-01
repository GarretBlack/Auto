$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$pythonw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$gui = Join-Path $PSScriptRoot "gui.pyw"

if (-not (Test-Path $pythonw)) {
    Write-Host "Не найден .\.venv\Scripts\pythonw.exe. Сначала выполните .\setup.ps1"
    exit 1
}

if (-not (Test-Path $gui)) {
    Write-Host "Не найден $gui"
    exit 1
}

Start-Process -FilePath $pythonw -ArgumentList $gui -WorkingDirectory $PSScriptRoot
