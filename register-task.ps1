param(
    [string]$TaskName = "AutoClicer",
    [string]$At = "09:00"
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $projectRoot "run.ps1"

if (-not (Test-Path $runScript)) {
    Write-Host "Файл run.ps1 не найден: $runScript"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$runScript`" -NoPrompt"

$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Запуск clicer.py через run.ps1 по расписанию" `
    -Force

Write-Host "Задача '$TaskName' зарегистрирована на $At"
