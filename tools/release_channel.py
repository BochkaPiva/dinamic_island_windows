# SPDX-License-Identifier: GPL-3.0-only
"""Publish bounded, version-specific release metadata without requiring GitHub API access."""
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from island import __version__,REPO_URL


def build_channel(directory,changelog):
    tag='v'+__version__
    section=re.search(r'^## '+re.escape(tag)+r'\s*\n(.*?)(?=^## |\Z)',changelog,re.M|re.S)
    if not section: raise ValueError('Missing release notes')
    assets=[]
    for name in (f'CloudIsland-Setup-{__version__}-win-x64.exe','SHA256SUMS.txt'):
        path=directory/name
        with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
        assets.append({'name':name,'size':path.stat().st_size,'browser_download_url':REPO_URL+'/releases/download/'+tag+'/'+name,
            'digest':'sha256:'+digest})
    return {'tag_name':tag,'html_url':REPO_URL+'/releases/tag/'+tag,'draft':False,'prerelease':False,
        'body':section.group(1).strip(),'assets':assets}


if __name__=='__main__':
    directory=Path(sys.argv[1])
    changelog=(Path(__file__).resolve().parents[1]/'CHANGELOG.md').read_text(encoding='utf-8')
    result=build_channel(directory,changelog)
    (directory/'update.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
