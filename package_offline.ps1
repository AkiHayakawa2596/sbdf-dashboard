$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$dist = Join-Path $root 'dist'
$stage = Join-Path $dist 'SBDF-Dashboard-Offline-Windows-x64'
$zip = Join-Path $dist 'SBDF-Dashboard-Offline-Windows-x64.zip'

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'data/csv') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'data/parquet') | Out-Null

Copy-Item 'server.py' $stage
Copy-Item 'config.json' $stage
Copy-Item 'requirements.txt' $stage
Copy-Item 'requirements-lock.txt' $stage
Copy-Item 'SHA256SUMS.txt' $stage
Copy-Item 'OFFLINE-INSTALL-WINDOWS.md' $stage
Copy-Item 'web' $stage -Recurse
Copy-Item 'wheelhouse' $stage -Recurse

$manifest = @"
SBDF Dashboard - Offline Windows x64
=====================================

This package intentionally contains NO custom EXE and NO BAT launcher.
Run the dashboard with an approved Python 3.12 x64 installation.

Contents:
- server.py                       Dashboard backend source
- config.json                     Editable SBDF source configuration
- web/                            Editable frontend
- wheelhouse/                     Windows x64 / CPython 3.12 wheels
- requirements-lock.txt           Exact package versions verified by GitHub Actions
- SHA256SUMS.txt                  SHA-256 hashes for audit/integrity checks
- OFFLINE-INSTALL-WINDOWS.md      Offline installation instructions

The GitHub Actions build verified:
1. wheels download as binary distributions,
2. installation succeeds with --no-index,
3. imports succeed,
4. requirements-lock.txt installs offline in a second clean venv,
5. the dashboard passes its /health endpoint.
"@
$manifest | Out-File -Encoding utf8 (Join-Path $stage 'PACKAGE-INFO.txt')

Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created $zip"
