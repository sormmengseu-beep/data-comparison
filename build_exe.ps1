param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

if (-not $SkipInstall) {
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt -r requirements-build.txt
}

python -m PyInstaller --noconfirm --clean DataComparisonVideoMaker.spec

$DistDir = Join-Path $ProjectRoot "dist\DataComparisonVideoMaker"
$ProjectsOut = Join-Path $DistDir "projects"
$ExportsOut = Join-Path $DistDir "exports"

New-Item -ItemType Directory -Force -Path $ProjectsOut, $ExportsOut | Out-Null

$SampleProjects = Join-Path $ProjectRoot "projects\*.dcvproject"
if (Test-Path -Path $SampleProjects) {
    Copy-Item -Path $SampleProjects -Destination $ProjectsOut -Force
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $DistDir\DataComparisonVideoMaker.exe"
Write-Host ""
Write-Host "Copy the whole dist\DataComparisonVideoMaker folder to another Windows PC."
