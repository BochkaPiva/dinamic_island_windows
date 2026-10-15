"""Extract the exact changelog section matching a release tag."""
from pathlib import Path
import re
import sys

tag = sys.argv[1]
if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
    raise SystemExit("Expected vX.Y.Z")
text = (Path(__file__).resolve().parents[1]/"CHANGELOG.md").read_text(encoding="utf-8")
match = re.search(r"^## " + re.escape(tag) + r"\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
if not match:
    raise SystemExit(f"No changelog entry for {tag}")
sys.stdout.reconfigure(encoding="utf-8")
print(match.group(1).strip())
