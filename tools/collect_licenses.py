"""Include dependency notices and metadata with both installer and portable ZIP."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
out = root / "build" / "licenses"
out.mkdir(parents=True, exist_ok=True)
for dist in distributions():
    name = dist.metadata["Name"]
    target = out / name
    for entry in dist.files or []:
        if "license" in entry.name.lower() or "copying" in entry.name.lower():
            source = Path(dist.locate_file(entry))
            if source.is_file():
                target.mkdir(exist_ok=True)
                shutil.copyfile(source, target / (str(entry).replace("/", "_").replace("\\", "_")))
    if target.exists():
        (target / "METADATA.txt").write_text(str(dist.metadata), encoding="utf-8")
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copyfile(python_license, out / "Python-LICENSE.txt")
print(f"Dependency notices: {out}")
