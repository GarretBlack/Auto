param(
    [string]$Config = ".\config.json",
    [int]$StartupDelay = -1,
    [int]$Cycles = -1,
    [string]$LogLevel = "",
    [switch]$NoPrompt
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Виртуальное окружение не найдено. Создайте .venv и установите зависимости из requirements.txt"
    exit 1
}

$args = @(
    ".\clicer.py",
    "--config", $Config
)

if ($StartupDelay -ge 0) {
    $args += @("--startup-delay", $StartupDelay)
}

if ($Cycles -gt 0) {
    $args += @("--cycles", $Cycles)
}

if ($LogLevel) {
    $args += @("--log-level", $LogLevel)
}

if ($NoPrompt) {
    $args += "--no-prompt"
}

& ".\.venv\Scripts\python.exe" @args
