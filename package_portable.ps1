param(
    [string]$DistRoot = "dist"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$AppDir = Join-Path $DistRoot "SBDF-Dashboard"
$ExePath = Join-Path $AppDir "SBDFDashboard.exe"
$ZipPath = Join-Path $DistRoot "SBDF-Dashboard-Portable.zip"

if (-not (Test-Path $ExePath)) {
    throw "PyInstaller output was not found: $ExePath"
}

Write-Host "Preparing portable deployment folder..."
Copy-Item "config.json" (Join-Path $AppDir "config.json") -Force

$WebTarget = Join-Path $AppDir "web"
if (Test-Path $WebTarget) {
    Remove-Item $WebTarget -Recurse -Force
}
Copy-Item "web" $WebTarget -Recurse -Force

Copy-Item "start.bat" (Join-Path $AppDir "Start Dashboard.bat") -Force
Copy-Item "PORTABLE-README.txt" (Join-Path $AppDir "PORTABLE-README.txt") -Force

$DataDir = Join-Path $AppDir "data"
$ParquetDir = Join-Path $DataDir "parquet"
$CsvDir = Join-Path $DataDir "csv"
New-Item -ItemType Directory -Path $ParquetDir -Force | Out-Null
New-Item -ItemType Directory -Path $CsvDir -Force | Out-Null

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Write-Host "Creating $ZipPath ..."
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal

if (-not (Test-Path $ZipPath)) {
    throw "Portable ZIP was not created."
}

$zipInfo = Get-Item $ZipPath
Write-Host "Portable ZIP ready: $($zipInfo.FullName) ($([math]::Round($zipInfo.Length / 1MB, 2)) MB)"
