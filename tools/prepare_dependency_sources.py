"""Download exact, unmodified library sources beside the public binary assets."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen
import zipfile

QT='6.11.2'
SOURCES=[(f'{module}-everywhere-src-{QT}.tar.xz',f'https://download.qt.io/archive/qt/6.11/{QT}/submodules/{module}-everywhere-src-{QT}.tar.xz',True)
    for module in ('qtbase','qtdeclarative','qtmultimedia','qtsvg','qtvirtualkeyboard','qtimageformats')]
SOURCES += [('pyside-setup-6.11.2.tar.gz','https://github.com/pyside/pyside-setup/archive/refs/tags/v6.11.2.tar.gz',False),
    ('ffmpeg-7.1.5.tar.xz','https://ffmpeg.org/releases/ffmpeg-7.1.5.tar.xz',False),
    ('zlib-1.3.1.tar.gz','https://zlib.net/fossils/zlib-1.3.1.tar.gz',False)]


def prepare(directory):
    directory=Path(directory);cache=directory/'dependency-source-cache';cache.mkdir(parents=True,exist_ok=True)
    def download(item):
        name,url,verify=item;path=cache/name
        if not path.exists():
            temp=path.with_suffix(path.suffix+'.part')
            with urlopen(url,timeout=90) as source,temp.open('wb') as out:
                while block:=source.read(1024*1024):out.write(block)
            temp.replace(path)
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if verify:
            expected=urlopen(url+'.sha256',timeout=30).read().decode().split()[0].lower()
            if digest!=expected:raise ValueError('Source checksum mismatch: '+name)
        print('Source ready: '+name,flush=True)
        return {'name':name,'url':url,'sha256':digest,'upstream_checksum_verified':verify,'size':path.stat().st_size}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:manifest=list(pool.map(download,SOURCES))
    root=Path(__file__).resolve().parents[1]
    target=directory/'Nelviro-0.10.0-dependency-sources.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as archive:
        for item in manifest:archive.write(cache/item['name'],'sources/'+item['name'])
        archive.writestr('sources.json',json.dumps(manifest,indent=2))
        for name in ('THIRD_PARTY.md','requirements.txt','legal/runtime-licenses/FFmpeg-NOTICE.txt','legal/runtime-licenses/LGPL-2.1.txt','legal/runtime-licenses/LGPL-3.0.txt','legal/runtime-licenses/GPL-3.0.txt'):
            archive.write(root/name,name)
        archive.writestr('README.txt','''Nelviro 0.10.0: unmodified corresponding dependency sources

Exact Qt/PySide version: 6.11.2; actual FFmpeg shared runtime: 7.1.5.
This archive accompanies installer and portable application binaries on the same release.
Application source and build/install scripts: the v0.10.0 tag of
https://github.com/BochkaPiva/dinamic_island_windows

Qt base supplies Core/Gui/Widgets/Network/OpenGL; declarative supplies Qml/Quick.
Other shipped Qt modules/plugins are supplied by multimedia, svg, virtualkeyboard
and imageformats. Qt Virtual Keyboard is distributed with this GPLv3 application.
Qt archives include bundled third-party sources and upstream build instructions.
PySide/shiboken sources are included in pyside-setup. Each archive retains its notices.
See sources.json for exact upstream URLs, byte sizes and SHA256 checksums.
FFmpeg-NOTICE.txt records the actual shared library's build configuration.

The libraries are not modified by Nelviro. Rebuilding the application:
install Python 3.14 x64, install requirements-dev.txt, run packaging/build.ps1.
To use a modified compatible Qt/PySide/FFmpeg build, replace its external files
under _internal/PySide6 (and matching bindings) in the installed onedir runtime.
No Qt DLL hash pinning is used. Rebuilding app binaries is also supported by GPLv3.
Follow the upstream build instructions inside each library archive; preserve ABI,
architecture, corresponding bindings and multimedia plugins as a matched set.
''')
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'sources':len(manifest)}))
    return target

if __name__=='__main__':prepare(sys.argv[1])
