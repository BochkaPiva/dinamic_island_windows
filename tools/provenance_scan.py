"""Read-only code/asset comparison. Evidence for an ownership review, not a legal clearance."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess


def git(repo,*args): return subprocess.check_output(['git','-C',str(repo),*args])


def large_functions(text):
    tree=ast.parse(text)
    result={}
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.end_lineno-node.lineno>=20:
            result[hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()]=node.name
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('original',type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    foreign={};assets={}
    original_ref='origin/main'
    for name in git(args.original,'ls-tree','-r','--name-only',original_ref).decode().splitlines():
        raw=git(args.original,'show',f'{original_ref}:{name}')
        if name.endswith('.py'):
            try: foreign.update({key:(name,function) for key,function in large_functions(raw.decode('utf-8-sig')).items()})
            except (SyntaxError,UnicodeError): pass
        elif Path(name).suffix.casefold() in {'.png','.ico','.ttf','.wav'}:
            assets[hashlib.sha256(raw).hexdigest()]=name
    records=[];matches=[];asset_matches=[]
    names=set(git(root,'ls-files').decode().splitlines())
    names.update(str(p.relative_to(root)).replace('\\','/') for p in (root/'island').rglob('*.py'))
    for name in sorted(names):
        path=root/name
        if not path.is_file(): continue
        raw=path.read_bytes()
        if name.startswith(('island/','main.py','packaging/')):
            records.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest()})
        if name.startswith('island/') and name.endswith('.py'):
            for key,function in large_functions(raw.decode('utf-8-sig')).items():
                if key in foreign: matches.append({'current':name,'function':function,'original':foreign[key]})
        if name.startswith(('island/assets/','packaging/')) and hashlib.sha256(raw).hexdigest() in assets:
            asset_matches.append({'current':name,'original':assets[hashlib.sha256(raw).hexdigest()]})
    value={'original_commit':git(args.original,'rev-parse',original_ref).decode().strip(),
        'application_baseline':git(root,'rev-parse','HEAD').decode().strip(),
        'comparison':'Exact AST matches of functions of at least 21 lines; exact binary asset hashes',
        'large_function_matches':matches,'asset_matches':asset_matches,'files':records,
        'legal_clearance':False,'limitations':'Does not detect rewritten/renamed/partial copies or prove ownership; inherited code and assets require owner review.'}
    target=root/'legal'/'provenance-code-scan.json'
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'large_function_matches':matches,'asset_matches':asset_matches,'scanned_files':len(records)},ensure_ascii=False))


if __name__=='__main__': main()
