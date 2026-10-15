# Third-party components

Cloud Island's application code is licensed under GPL-3.0-only (see LICENSE).
Copyright (c) 2026 Cloud Island contributors.

The application shell, media adapter, settings, drawing, release integration and
build scripts are independently implemented for this repository. The new hub,
cursor-motion and output-spectrum modules were authored during development of
the personal prototype and carried over with their original authored code.
No code, icon or translation files from Faygooich/Glassy-Music-Widget are shipped.

Dependencies retain their own copyright and license terms. Release packages
include notices copied from the installed distributions in `licenses/`; the EXE
also bundles them. The corresponding application source is attached to each release.

| Component | Source / license information |
| --- | --- |
| PyQt6 | https://www.riverbankcomputing.com/software/pyqt/ — GPL v3 |
| Qt 6 | https://code.qt.io/cgit/qt/ — Qt open-source licenses; see bundled notices |
| NumPy | https://github.com/numpy/numpy — BSD-3-Clause and bundled notices |
| PyAudioWPatch / PortAudio | https://github.com/s0d3s/PyAudioWPatch — MIT and bundled notices |
| PyWinRT | https://github.com/pywinrt/pywinrt — MIT |
| Golos Text | https://github.com/GoogleFonts/golos-text — SIL Open Font License 1.1; `island/assets/fonts/OFL.txt` |
| CPython | https://www.python.org/ — PSF license and notices |
| PyInstaller bootloader | https://github.com/pyinstaller/pyinstaller — GPL with bootloader exception |

Font files are used under their OFL license. Product names of Windows, Apple and
media services identify compatibility; this application is not affiliated with them.
