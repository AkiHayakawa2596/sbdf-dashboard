# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the portable Windows SBDF Dashboard.

Build on Windows with build_portable.bat.  The generated folder under
`dist/SBDF-Dashboard/` can be copied to another Windows PC and run without
installing Python or pip packages there.
"""

from PyInstaller.utils.hooks import collect_all, copy_metadata

block_cipher = None

datas = [
    ("web", "web"),
    ("config.json", "."),
]
binaries = []
hiddenimports = []

# Spotfire and DuckDB can contain package data/native components that are not
# always visible to PyInstaller's static import scan. Collect them explicitly.
for package in ("spotfire", "duckdb"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# Preserve distribution metadata used by some runtime packages.
for package in ("Flask", "pandas", "requests", "spotfire", "duckdb"):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

a = Analysis(
    ["server.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SBDFDashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SBDF-Dashboard",
)
