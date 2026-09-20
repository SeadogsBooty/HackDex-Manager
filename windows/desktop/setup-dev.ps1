param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$Repo = Resolve-Path (
    Join-Path $PSScriptRoot "..\.."
)

Set-Location $Repo

$Venv = Join-Path $Repo ".venv-windows"

if ($Recreate -and (Test-Path $Venv)) {
    Remove-Item `
        -Recurse `
        -Force `
        $Venv
}

if (-not (Test-Path $Venv)) {
    py -3 -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"

& $Python -m pip install --upgrade pip

& $Python -m pip install `
    -r requirements.txt

& $Python -m pip install `
    -r windows\requirements-windows.txt

Write-Host ""
Write-Host "Windows environment ready:"
Write-Host "  $Venv"
