"""Include dependency notices and metadata with both installer and portable ZIP."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
out = root / "build" / "licenses"
out.mkdir(parents=True, exist_ok=True)
runtime_names=('PySide6-Essentials','shiboken6','numpy','PyAudioWPatch','winrt-runtime',
    'winrt-Windows.Foundation','winrt-Windows.Foundation.Collections','winrt-Windows.Media.Control',
    'winrt-Windows.Storage.Streams','typing_extensions','cryptography','cffi','pycparser','pyinstaller')
for dist in map(distribution,runtime_names):
    name = dist.metadata["Name"]
    target = out / name
    for entry in dist.files or []:
        if "license" in entry.name.lower() or "copying" in entry.name.lower():
            source = Path(dist.locate_file(entry))
            if source.is_file():
                target.mkdir(exist_ok=True)
                shutil.copyfile(source, target / (str(entry).replace("/", "_").replace("\\", "_")))
    if target.exists():
        # Preserve raw metadata: serializing legacy email headers rejects some
        # valid multi-line descriptions on Python 3.14 (for example altgraph).
        (target / "METADATA.txt").write_text(dist.read_text("METADATA") or
                                            dist.read_text("PKG-INFO") or name, encoding="utf-8")
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copyfile(python_license, out / "Python-LICENSE.txt")
for path in (root/'legal'/'runtime-licenses').glob('*.txt'):
    shutil.copy2(path,out/path.name)
if not (out/'LGPL-3.0.txt').is_file(): raise SystemExit('Missing LGPL text')
print(f"Dependency notices: {out}")
