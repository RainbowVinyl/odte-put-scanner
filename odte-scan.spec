# -*- mode: python ; coding: utf-8 -*-
# pyinstaller --noconfirm odte-scan.spec

a = Analysis(
    ["scanner.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("config.json", "."),
        ("events.json", "."),
        ("chain.example.json", "."),
        ("integrations.example.json", "."),
    ],
    hiddenimports=["brokers", "integrations"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="odte-scan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
