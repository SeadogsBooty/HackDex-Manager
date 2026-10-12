param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"

$Repo = Resolve-Path (
    Join-Path $PSScriptRoot "..\.."
)

Set-Location $Repo


if (-not $SkipAppBuild) {

    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File ".\windows\desktop\build.ps1" `
        -Clean

    if ($LASTEXITCODE -ne 0) {
        throw "HackDex application build failed."
    }
}


$Candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)


$PF86 = ${env:ProgramFiles(x86)}

if ($PF86) {
    $Candidates += (
        Join-Path $PF86 "Inno Setup 6\ISCC.exe"
    )
}


$ISCC = $Candidates |
    Where-Object {
        $_ -and (Test-Path $_)
    } |
    Select-Object -First 1


if (-not $ISCC) {
    throw "Inno Setup 6 compiler was not found."
}


Write-Host ""
Write-Host "Inno Setup compiler:"
Write-Host "  $ISCC"


$Iss = Join-Path `
    $Repo `
    "windows\installer\HackDexManager.iss"


# Keep the Windows installer version synchronized with the
# authoritative HackDex Manager application version.
$VersionFile = Join-Path `
    $Repo `
    "app\version.py"

$VersionSource = Get-Content `
    -LiteralPath $VersionFile `
    -Raw

$VersionMatch = [regex]::Match(
    $VersionSource,
    'APP_VERSION\s*=\s*"([^"]+)"'
)

if (-not $VersionMatch.Success) {
    throw "Unable to read APP_VERSION from app\version.py."
}

$AppVersion = (
    $VersionMatch
        .Groups[1]
        .Value
)


$InstallerSource = Get-Content `
    -LiteralPath $Iss `
    -Raw

$InstallerVersionMatch = [regex]::Match(
    $InstallerSource,
    '#define\s+MyAppVersion\s+"([^"]+)"'
)

if (-not $InstallerVersionMatch.Success) {
    throw "Unable to read MyAppVersion from HackDexManager.iss."
}

$InstallerVersion = (
    $InstallerVersionMatch
        .Groups[1]
        .Value
)

if ($InstallerVersion -ne $AppVersion) {
    throw (
        "Windows installer version mismatch. "
        + "app/version.py = "
        + $AppVersion
        + "; HackDexManager.iss = "
        + $InstallerVersion
    )
}

Write-Host ""
Write-Host "HackDex Manager application version: $AppVersion"
Write-Host "Windows installer version:          $InstallerVersion"
Write-Host ""

& $ISCC $Iss

if ($LASTEXITCODE -ne 0) {
    throw "Installer compilation failed."
}


$Setup = Join-Path `
    $Repo `
    "windows\installer\output\HackDex Manager Setup.exe"


if (-not (Test-Path $Setup)) {
    throw "Installer was not produced."
}


Write-Host ""
Write-Host "Installer:"
Write-Host "  $Setup"
