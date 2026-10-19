# SPDX-License-Identifier: GPL-3.0-only
"""Central local capabilities; licensing is independent of power/runtime policy."""
from dataclasses import dataclass
import json
from pathlib import Path
import time
import uuid
from PySide6.QtCore import QObject, Signal
from . import build_config
from .signed_payload import verify_envelope
from .protected_storage import protect,unprotect

FREE_FEATURES=frozenset({'island.overview','search.basic','notes.local','timer.basic','desktop.groups'})
PRO_FEATURES=FREE_FEATURES | frozenset({'island.focus','island.notes','island.mirror','island.video',
    'island.pin','island.floating','files.bridge','desktop.widgets','workspaces.scenes'})
FREE_LIMITS={'desktop.groups.active':2,'desktop.widgets.active':1}
PRO_LIMITS={'desktop.groups.active':None,'desktop.widgets.active':None}
# Preserve current island utilities; membership adds groups and future optional modules.
COMMUNITY_BASE_FEATURES = PRO_FEATURES - frozenset({'island.mirror','island.video','island.floating','desktop.widgets'})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str=''
    limit: int | None=None


@dataclass(frozen=True)
class Grant:
    edition: str
    features: frozenset
    limits: dict
    valid_until: int=0


def free_grant(): return Grant('free',FREE_FEATURES,dict(FREE_LIMITS))


def verify_license(envelope,keys,installation_id,now=None):
    now=time.time() if now is None else now
    value=verify_envelope(envelope,keys,'cloud-hub/license/v1')
    if type(value.get('schema')) is not int or value.get('schema')!=1 or value.get('product')!=build_config.PRODUCT_ID:
        raise ValueError('License belongs to a different product')
    if value.get('installation_id')!=installation_id or value.get('edition')!='pro':
        raise ValueError('License belongs to a different installation')
    times=[value.get(k) for k in ('issued_at','not_before','offline_until','paid_until')]
    if any(type(v) is not int or v<0 for v in times): raise ValueError('Invalid license dates')
    issued,start,offline,paid=times
    if not issued<=start<=offline<=paid or issued>now+300 or not start<=now<offline:
        raise ValueError('License expired or not yet valid')
    features=value.get('features')
    limits=value.get('limits')
    if not isinstance(features,list) or any(not isinstance(f,str) or f not in PRO_FEATURES for f in features):
        raise ValueError('Invalid capabilities')
    if not isinstance(limits,dict) or any(k not in PRO_LIMITS or
            (v is not None and (type(v) is not int or v<0)) for k,v in limits.items()):
        raise ValueError('Invalid capability limits')
    # Missing fields never turn into unlimited access.
    return Grant('pro',FREE_FEATURES|frozenset(features),{**FREE_LIMITS,**limits},offline)


class FeatureAccess(QObject):
    changed=Signal()

    def __init__(self,directory,distribution=None,keys=None,clock=None):
        super().__init__()
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.distribution=build_config.DISTRIBUTION if distribution is None else distribution
        self.keys=build_config.LICENSE_PUBLIC_KEYS if keys is None else keys
        self.clock=clock or time.time
        self.grant=free_grant()
        self.reason=''
        self.storage_available=True
        try: self.installation_id=self._identity()
        except OSError:
            self.storage_available=False
            self.installation_id=str(uuid.uuid4())
        self.reload()

    def _identity(self):
        path=self.directory/'installation-id.bin'
        try: return str(uuid.UUID(unprotect(path.read_bytes()).decode('ascii')))
        except (OSError,ValueError):
            identifier=str(uuid.uuid4())
            temporary=path.with_suffix('.tmp')
            temporary.write_bytes(protect(identifier.encode('ascii')));temporary.replace(path)
            return identifier

    def reload(self):
        self.reason=''
        self.grant=free_grant()
        if self.distribution=='preview':
            self.grant=Grant('preview',PRO_FEATURES,dict(PRO_LIMITS))
        elif self.distribution=='community':
            self.grant=Grant('free',COMMUNITY_BASE_FEATURES,dict(FREE_LIMITS))
            from .community_access import PermitStore
            permit = PermitStore(self.directory, build_config.COMMUNITY_PUBLIC_KEYS,
                self.installation_id, build_config.COMMUNITY_CHANNEL_ID, clock=self.clock).load()
            if permit and permit.allows(self.clock()):
                self.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS),
                                 min(permit.expires_at,permit.access_until))
        elif not self.storage_available:
            self.reason='Защищённое хранилище Windows недоступно'
        else:
            try:
                self.grant=verify_license((self.directory/'license.json').read_bytes(),
                    self.keys,self.installation_id,self.clock())
            except (OSError,ValueError): self.reason='Нет действующей лицензии'
        self.changed.emit()

    def install_license(self,document):
        # Check before replacing a known-good grant. No private key or payment callback trusted here.
        verify_license(document,self.keys,self.installation_id,self.clock())
        path=self.directory/'license.json'
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
        temporary.replace(path)
        self.reload()

    def _expire(self):
        if self.grant.valid_until and self.clock()>=self.grant.valid_until:
            self.grant=Grant('free',COMMUNITY_BASE_FEATURES,dict(FREE_LIMITS)) if self.distribution=='community' else free_grant()
            self.reason='Срок офлайн-разрешения истёк'
            self.changed.emit()

    def feature(self,key):
        self._expire()
        return Decision(key in self.grant.features,'' if key in self.grant.features else
            'Доступно подписчикам канала' if self.distribution=='community' else 'Нужна лицензия Pro')

    def capacity(self,key,current,addition=1):
        self._expire()
        if key not in FREE_LIMITS or type(current) is not int or type(addition) is not int or min(current,addition)<0:
            return Decision(False,'Неизвестное ограничение')
        limit=self.grant.limits[key]
        allowed=limit is None or current+addition<=limit
        return Decision(allowed,'' if allowed else
            'В базовом доступе две группы. Дополнительные доступны через раздел «Сообщество».'
            if self.distribution=='community' else 'Достигнут лимит активных групп',limit)

    def active_ids(self,records):
        self._expire()
        limit=self.grant.limits['desktop.groups.active']
        return {g['id'] for g in (records if limit is None else records[:limit])}
