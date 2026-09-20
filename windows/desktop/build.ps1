param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$Repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Repo

$Python = Join-Path $Repo ".venv-windows\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Windows development environment is missing. Run windows\desktop\setup-dev.ps1 first."
}

$BuildRoot = Join-Path $Repo "windows\build"
$DistRoot = Join-Path $Repo "windows\dist"
$SpecFile = Join-Path $Repo "windows\desktop\HackDexManager.spec"

if ($Clean) {
    if (Test-Path $BuildRoot) {
        Remove-Item -Recurse -Force $BuildRoot
    }

    if (Test-Path $DistRoot) {
        Remove-Item -Recurse -Force $DistRoot
    }
}

New-Item -ItemType Directory -Force $BuildRoot | Out-Null
New-Item -ItemType Directory -Force $DistRoot | Out-Null

$env:HACKDEX_DESKTOP = "1"

Write-Host ""
Write-Host "Running PyInstaller..."
Write-Host ""

& $Python `
    -m PyInstaller `
    --noconfirm `
    --clean `
    --workpath $BuildRoot `
    --distpath $DistRoot `
    $SpecFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

$AppDir = Join-Path $DistRoot "HackDex Manager"
$Exe = Join-Path $AppDir "HackDex Manager.exe"

if (-not (Test-Path $Exe)) {
    throw "Expected packaged executable was not produced: $Exe"
}

$ExeInfo = Get-Item $Exe
$LauncherMB = [math]::Round($ExeInfo.Length / 1MB, 2)

$TotalBytes = (
    Get-ChildItem $AppDir -Recurse -File |
    Measure-Object -Property Length -Sum
).Sum

$TotalMB = [math]::Round($TotalBytes / 1MB, 2)

Write-Host ""
Write-Host "============================================================"
Write-Host " HACKDEX MANAGER WINDOWS BUILD COMPLETE"
Write-Host "============================================================"
Write-Host ""
Write-Host "Executable:"
Write-Host "  $Exe"
Write-Host ""
Write-Host "Launcher size: $LauncherMB MB"
Write-Host "Application size: $TotalMB MB"
Write-Host ""
Write-Host "Application folder:"
Write-Host "  $AppDir"
Write-Host "============================================================"
