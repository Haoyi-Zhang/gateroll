#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,pathlib

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default=None); ap.add_argument('--output',required=True); a=ap.parse_args()
    root=pathlib.Path(a.root).resolve() if a.root else pathlib.Path(__file__).resolve().parents[1]
    d=root/'inputs'/'public-history'; manifest=json.loads((d/'public-history-audit.json').read_text()); failures=[]
    for p in manifest['pairs']:
        for side in ('old','new'):
            fn=p[f'{side}_file']; expected=p[f'{side}_sha256']; path=d/'raw'/fn
            if not path.is_file(): failures.append(f'missing:{fn}'); continue
            got=hashlib.sha256(path.read_bytes()).hexdigest()
            if got!=expected:failures.append(f'hash:{fn}')
    result={'schema':'gateroll.public-history-verification.v1','pair_count':manifest['pair_count'],'failures':failures,'pass':not failures,'claim_boundary':manifest['claim_boundary']}
    pathlib.Path(a.output).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    if failures: raise SystemExit(1)
if __name__=='__main__':main()
