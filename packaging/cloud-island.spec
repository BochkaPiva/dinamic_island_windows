# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
analysis = Analysis([str(root / "main.py")], pathex=[str(root)],
    datas=[(str(root / "island" / "assets"), "island/assets"),
           (str(root / "LICENSE"), "."), (str(root / "THIRD_PARTY.md"), "."),
           (str(root / "build" / "licenses"), "licenses")],
    hiddenimports=collect_submodules("winrt"),
    excludes=["PIL", "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6.QtTest",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore"], noarchive=False)
# Never take incompatible, unversioned ICU DLLs from unrelated tools on PATH.
analysis.binaries = [b for b in analysis.binaries
                     if not os.path.basename(b[0]).lower().startswith("icu")
                     and os.path.basename(b[0]).lower() not in {"opengl32sw.dll", "qt6pdf.dll"}]
archive = PYZ(analysis.pure)
exe = EXE(archive, analysis.scripts, [], exclude_binaries=True,
          name="CloudIsland", console=False, debug=False, strip=False, upx=False,
          icon=str(root / "packaging" / "cloud.ico"),
          version=str(root / "build" / "version_info.txt"))
bundle = COLLECT(exe, analysis.binaries, analysis.datas, name="CloudIsland", strip=False, upx=False)
