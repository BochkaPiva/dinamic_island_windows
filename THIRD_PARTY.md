# Third-party components

This is the private PySide6 commercial-development line. Earlier public releases
remain GPL-3.0-only. The candidate terms and outstanding ownership review are in
LICENSE and legal/. Do not redistribute this candidate as a sales release.

The application shell, media adapter, settings, drawing, release integration and
build scripts are independently implemented for this repository. The new hub,
cursor-motion and output-spectrum modules were authored during development of
the personal prototype and carried over with their original authored code.
No code, icon or translation files from Faygooich/Glassy-Music-Widget are shipped.

Dependencies retain their own copyright and license terms. Release packages
include dependency notices and GPL/LGPL texts in `licenses/`. LGPL libraries are
external shared files under `_internal/`, replaceable by compatible builds.
The commercial workflow does not publish application-source archives.
Corresponding dependency sources and their delivery must be approved before
public distribution (legal/release-approvals.json).

| Component | Source / license information |
| --- | --- |
| PySide6 Essentials / shiboken6 | https://code.qt.io/cgit/pyside/pyside-setup.git/ — LGPL v3 option; version 6.11.2 |
| Qt 6 | https://code.qt.io/cgit/qt/ — Qt open-source licenses; see bundled notices |
| NumPy | https://github.com/numpy/numpy — BSD-3-Clause and bundled notices |
| PyAudioWPatch / PortAudio | https://github.com/s0d3s/PyAudioWPatch — MIT and bundled notices |
| PyWinRT | https://github.com/pywinrt/pywinrt — MIT |
| Golos Text | https://github.com/GoogleFonts/golos-text — SIL Open Font License 1.1; `island/assets/fonts/OFL.txt` |
| CPython | https://www.python.org/ — PSF license and notices |
| cryptography / cffi / pycparser | https://cryptography.io/ and distribution notices — their respective Apache/BSD/MIT licenses |
| PyInstaller bootloader | https://github.com/pyinstaller/pyinstaller — GPL with bootloader exception |

Font files are used under their OFL license. Product names of Windows, Apple and
media services identify compatibility; this application is not affiliated with them.

The account service has an isolated dependency lock in `server/requirements.txt`
and is not bundled into the desktop runtime. It uses Django, Authlib,
django-oauth-toolkit, OAuthlib, requests, psycopg, cryptography and WhiteNoise,
with their transitive distribution notices. Linux deployment additionally uses
Gunicorn. Their complete notices, supported deployment versions, and security
review are part of server launch approval; installing the pinned environment and
passing `pip check` do not replace that review. Authentication and payment brand
names identify the intended integrations; no provider accounts are provisioned
by this source commit.
