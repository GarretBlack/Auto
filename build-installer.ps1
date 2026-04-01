$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$requirementsFile = Join-Path $root "requirements-build.txt"
$iconScript = Join-Path $root "tools\generate_icon.py"
$iconPath = Join-Path $root "assets\emulation-work.ico"
$guiEntry = Join-Path $root "gui.pyw"
$installerScript = Join-Path $root "installer.iss"
if (-not (Test-Path $python)) {
    throw "Missing .venv\\Scripts\\python.exe. Run .\\setup.ps1 first."
}

Write-Host "Installing build dependencies..."
& $python -m pip install -r $requirementsFile

Write-Host "Generating icon..."
& $python $iconScript

$configData = (Join-Path $root "config.json") + ";."
$assetsData = (Join-Path $root "assets") + ";assets"

$buildDir = Join-Path $root "build"
$distDir = Join-Path $root "dist"
$specPath = Join-Path $root "EmulationWork.spec"

foreach ($path in @($buildDir, $distDir)) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
if (Test-Path $specPath) {
    Remove-Item -LiteralPath $specPath -Force
}

Write-Host "Building standalone exe..."
$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "EmulationWork",
    "--icon", $iconPath,
    "--add-data", $configData,
    "--add-data", $assetsData,
    "--hidden-import", "pynput.keyboard._win32",
    "--hidden-import", "pynput.mouse._win32",
    "--collect-all", "pyautogui",
    "--collect-all", "mouseinfo",
    "--collect-all", "pynput",
    $guiEntry
)
& $python @pyinstallerArgs

function Get-IsccPath {
    $command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $known = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $known) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

$iscc = Get-IsccPath
if (-not $iscc) {
    Write-Host "Inno Setup not found. Installing via winget..."
    winget install --exact --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements --disable-interactivity
    $iscc = Get-IsccPath
}

if (-not $iscc) {
    throw "Unable to find ISCC.exe after installing Inno Setup."
}

Write-Host "Building installer..."
& $iscc $installerScript

$exePath = Join-Path $root "dist\EmulationWork.exe"
$setupPath = Join-Path $root "dist\installer\EmulationWorkSetup.exe"

if (-not (Test-Path $exePath)) {
    throw "Built exe not found: $exePath"
}
if (-not (Test-Path $setupPath)) {
    throw "Built installer not found: $setupPath"
}

Write-Host ""
Write-Host "Done."
Write-Host "EXE:   $exePath"
Write-Host "SETUP: $setupPath"
