# SPDX-License-Identifier: GPL-3.0-only
"""Candidate checks are executable; sales gates remain explicit until configured."""
import argparse
import base64
import importlib.metadata
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from island import build_config as config


def problems(sales=False):
    issues=[]
    for name in ('PyQt6','PyQt6-Qt6','PyQt6-sip','PySide6-Addons'):
        try: importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: continue
        issues.append('Unexpected dependency: '+name)
    if sales:
        if config.DISTRIBUTION!='commercial': issues.append('Preview distribution cannot be sold')
        if not config.PUBLIC_RELEASE_REPOSITORY or config.PUBLIC_RELEASE_REPOSITORY=='BochkaPiva/dinamic_island_windows':
            issues.append('Commercial releases need a separate binary release repository')
        for name in ('UPDATE_CHANNEL_URL','LICENSE_API_URL','ACCOUNT_API_ORIGIN'):
            if not getattr(config,name).startswith('https://'): issues.append(name+' is not configured')
        for name in ('LICENSE_PUBLIC_KEYS','UPDATE_PUBLIC_KEYS'):
            keys=getattr(config,name)
            if not keys: issues.append(name+' is not configured')
            for value in keys.values():
                try:
                    if len(base64.b64decode(value,validate=True))!=32: raise ValueError()
                except ValueError: issues.append(name+' contains an invalid key')
        root=Path(__file__).resolve().parents[1]
        try: approvals=json.loads((root/'legal'/'release-approvals.json').read_text(encoding='utf-8'))
        except (OSError,ValueError): approvals={}
        for key in ('code_rights','dependency_sources','seller_documents','payment_lifecycle','signed_installer','commercial_channel'):
            if approvals.get(key) is not True: issues.append('Not approved: '+key)
    return issues


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sales',action='store_true');parser.add_argument('--candidate',action='store_true')
    args=parser.parse_args()
    issues=problems(args.sales)
    print(json.dumps({'candidate':not args.sales,'ready':not issues,'issues':issues},indent=2))
    sys.exit(bool(issues))
