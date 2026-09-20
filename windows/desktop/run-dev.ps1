param()

$ErrorActionPreference = "Stop"

$Repo = Resolve-Path (
    Join-Path $PSScriptRoot "..\.."
)

$Python = Join-Path `
    $Repo `
    ".venv-windows\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Windows development environment is missing. Run setup-dev.ps1 first."
}

Set-Location $Repo

$env:HACKDEX_DESKTOP = "1"

& $Python `
    windows\desktop\launcher.py
