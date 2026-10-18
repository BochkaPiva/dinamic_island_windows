# SPDX-License-Identifier: GPL-3.0-only
"""Own small shortcut files; commit group references before collecting desktop copies."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
from PySide6.QtCore import QStandardPaths


def desktop_directories():
    result=[Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation))]
    if os.name=='nt':
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,0x19,None,0,buffer)==0:
            result.append(Path(buffer.value))
    return result


def path_key(path):
    return os.path.normcase(os.path.abspath(path))


class ShortcutLibrary:
    def __init__(self,directory,desktop_roots=None):
        self.root=Path(directory)/'shortcuts'
        self.manifest=Path(directory)/'shortcut-library.json'
        self.desktop_roots=desktop_directories() if desktop_roots is None else [Path(p) for p in desktop_roots]
        self.entries={}
        try:
            document=json.loads(self.manifest.read_text(encoding='utf-8'))
            for relative,record in document.get('entries',{}).items():
                if isinstance(record,dict) and self.owns(self.root/relative) and isinstance(record.get('origin'),str):
                    self.entries[relative]=record
        except (OSError,ValueError,TypeError,AttributeError):
            if self.manifest.exists():
                import shutil
                shutil.copy2(self.manifest,self.manifest.with_suffix('.recovery.json'))

    def owns(self,path):
        path=Path(path)
        return path.suffix.casefold() in {'.lnk','.url'} and path.resolve().is_relative_to(self.root.resolve())

    def on_desktop(self,path):
        return any(path_key(Path(path).parent)==path_key(root) for root in self.desktop_roots)

    def save(self):
        self.manifest.parent.mkdir(parents=True,exist_ok=True)
        temp=self.manifest.with_suffix('.tmp')
        temp.write_text(json.dumps({'version':1,'entries':self.entries},ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.manifest)

    def capture(self,path,origin=None):
        """Return a durable copy. Do not remove the source at this stage."""
        source=Path(path)
        if self.owns(source):
            return str(source)
        if source.suffix.casefold() not in {'.lnk','.url'}:
            return str(source)
        if source.is_symlink() or not source.is_file() or source.stat().st_size>4*1024*1024:
            raise OSError('Ярлык недоступен или имеет неподдерживаемый размер')
        content=source.read_bytes()
        digest=hashlib.sha256(content).hexdigest()
        original=str(Path(origin) if origin is not None else source.absolute())
        identifier=hashlib.sha256((path_key(original)+'\0'+digest).encode('utf-8')).hexdigest()[:32]
        destination=self.root/identifier/source.name
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            if destination.read_bytes()!=content:
                raise OSError('Сохранённый ярлык изменён; исходный файл оставлен на месте')
        else:
            # Atomic installation; never overwrite an existing shortcut.
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.tmp',delete=False) as stream:
                    temporary=Path(stream.name)
                    stream.write(content)
                temporary.replace(destination)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        relative=destination.relative_to(self.root).as_posix()
        previous=self.entries.get(relative)
        self.entries[relative]={'origin':original,'sha256':digest}
        try:
            self.save()
        except OSError:
            if previous is None: self.entries.pop(relative,None)
            else: self.entries[relative]=previous
            raise
        return str(destination)

    def collect(self,path):
        """Remove only a verified matching desktop shortcut, after group commit."""
        stored=Path(path)
        if not self.owns(stored):
            return False
        record=self.entries.get(stored.relative_to(self.root).as_posix())
        if not record:
            return False
        source=Path(record['origin'])
        if not self.on_desktop(source) or not source.exists():
            return False
        if source.is_symlink() or not source.is_file() or source.suffix.casefold() not in {'.lnk','.url'}:
            raise OSError('Исходный ярлык изменился; он оставлен на рабочем столе')
        digest=record.get('sha256')
        if hashlib.sha256(stored.read_bytes()).hexdigest()!=digest or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise OSError('Ярлык изменился; исходный файл оставлен на рабочем столе')
        source.unlink()
        return True

    def restore(self,path):
        source=Path(path)
        if not self.owns(source):
            raise OSError('Этот ярлык не находится в библиотеке Cloud Hub')
        destination=self.desktop_roots[0]/source.name
        destination.parent.mkdir(parents=True,exist_ok=True)
        content=source.read_bytes()
        if destination.exists():
            if destination.read_bytes()==content:
                return destination
            raise OSError('На рабочем столе уже есть другой ярлык с этим названием')
        with destination.open('xb') as stream:
            stream.write(content)
        return destination
