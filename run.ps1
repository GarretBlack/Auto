param(
    [int]$StartupDelay = 5,
    [int]$Cycles = 1,
    [switch]$NoPrompt
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Виртуальное окружение не найдено. Создайте .venv и установите зависимости из requirements.txt"
    exit 1
}

$args = @(
    ".\clicer.py",
    "--startup-delay", $StartupDelay,
    "--cycles", $Cycles
)

if ($NoPrompt) {
    $args += "--no-prompt"
}

& ".\.venv\Scripts\python.exe" @args
