# SPDX-License-Identifier: GPL-3.0-only
"""Reject accidental proprietary-source/development or disallowed Qt payloads."""
import json
from pathlib import Path
import sys


def audit(root):
    files=[p for p in root.rglob('*') if p.is_file()]
    issues=[]
    for path in files:
        name=path.name.casefold()
        relative=str(path.relative_to(root)).replace('\\','/').casefold()
        if 'pyqt' in relative or 'webengine' in name: issues.append(str(path.relative_to(root)))
        if name.startswith(('qt6charts','qt6datavisualization','qt6pdf','qt6test')): issues.append(str(path.relative_to(root)))
        if path.suffix.casefold() in {'.py','.pyx','.h','.cpp','.pem','.key'} and 'licenses/' not in relative:
            issues.append(str(path.relative_to(root)))
    runtime=root/'_internal'/'PySide6'
    for name in ('Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6Network.dll'):
        if not (runtime/name).exists(): issues.append('Missing shared library: '+name)
    if not (root/'CloudIsland.exe').exists(): issues.append('Missing application')
    result={'files':len(files),'issues':issues,'qt_libraries':[p.name for p in runtime.glob('Qt6*.dll')]}
    return result


if __name__=='__main__':
    result=audit(Path(sys.argv[1]))
    print(json.dumps(result,indent=2))
    sys.exit(bool(result['issues']))
