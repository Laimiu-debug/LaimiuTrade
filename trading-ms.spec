# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建步骤（Windows）：
  1. cd frontend && npm run build
  2. backend\.venv\Scripts\pip install pyinstaller
  3. backend\.venv\Scripts\pyinstaller --noconfirm --clean trading-ms.spec
产物：dist/TradingMS.exe（数据保存在 exe 同目录 data/ 下）
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("frontend/dist", "frontend_dist"),
    ("backend/assets/icon.png", "assets"),
]
binaries = []
hiddenimports = collect_submodules("uvicorn") + ["pystray", "PIL", "PIL.Image", "PIL.ImageDraw"]

# akshare 依赖大量包内数据文件，整体收集
ak_datas, ak_binaries, ak_hidden = collect_all("akshare")
datas += ak_datas
binaries += ak_binaries
hiddenimports += ak_hidden

# pystray 在 Windows 上依赖 pywin32
try:
    pystray_datas, pystray_binaries, pystray_hidden = collect_all("pystray")
    datas += pystray_datas
    binaries += pystray_binaries
    hiddenimports += pystray_hidden
except Exception:
    pass

a = Analysis(
    ["backend/launcher.py"],
    pathex=["backend"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "PyQt5", "PySide2", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TradingMS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="backend/assets/icon.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
