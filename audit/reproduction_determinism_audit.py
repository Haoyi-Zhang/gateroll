#!/usr/bin/env python3
"""Compare two clean reproductions after removing measurement-only fields."""
from __future__ import annotations
import argparse,csv,hashlib,json,re
from pathlib import Path
from typing import Any

VOLATILE=(
 'time','latency','duration','elapsed','cpu','rss','memory','timestamp','started','finished',
 'wall','peak','pid','port','hostname','host_name','absolute_path','workdir','output_dir',
 'resource_usage','measurement','throughput'
)

def volatile_key(k:str)->bool:
    s=k.lower().replace('-','_')
    return any(v in s for v in VOLATILE)

def normalize_json(x:Any)->Any:
    if isinstance(x,dict):
        return {k:normalize_json(v) for k,v in sorted(x.items()) if not volatile_key(k)}
    if isinstance(x,list):
        return [normalize_json(v) for v in x]
    if isinstance(x,str):
        if x.startswith('/mnt/') or x.startswith('/tmp/'):
            return '<ABSOLUTE_PATH>'
        return x
    return x

def digest_obj(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def normalize_csv(path:Path)->Any:
    with path.open(newline='') as f:
        r=csv.DictReader(f)
        rows=[]
        keep=[c for c in (r.fieldnames or []) if not volatile_key(c)]
        for row in r:
            rows.append({c:('<ABSOLUTE_PATH>' if str(row.get(c,'')).startswith(('/mnt/','/tmp/')) else row.get(c,'')) for c in keep})
    rows.sort(key=lambda d:json.dumps(d,sort_keys=True,separators=(',',':')))
    return {'columns':keep,'rows':rows}

def normalized_digest(path:Path)->str|None:
    try:
        if path.suffix.lower()=='.json': return digest_obj(normalize_json(json.loads(path.read_text())))
        if path.suffix.lower()=='.csv': return digest_obj(normalize_csv(path))
    except Exception:
        return None
    return None

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--left',type=Path,required=True);ap.add_argument('--right',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();left=a.left.resolve();right=a.right.resolve()
    lf={p.relative_to(left):p for p in left.rglob('*') if p.is_file() and p.suffix.lower() in ('.json','.csv')}
    rf={p.relative_to(right):p for p in right.rglob('*') if p.is_file() and p.suffix.lower() in ('.json','.csv')}
    common=sorted(set(lf)&set(rf));results=[];mismatch=[];unreadable=[]
    for rel in common:
        dl=normalized_digest(lf[rel]);dr=normalized_digest(rf[rel])
        rec={'path':str(rel),'left_digest':dl,'right_digest':dr,'match':dl is not None and dl==dr}
        results.append(rec)
        if dl is None or dr is None: unreadable.append(str(rel))
        elif dl!=dr: mismatch.append(str(rel))
    semantic={'left_file_count':len(lf),'right_file_count':len(rf),'common_compared':len(common),'left_only':sorted(map(str,set(lf)-set(rf))),'right_only':sorted(map(str,set(rf)-set(lf))),'mismatches':mismatch,'unreadable':unreadable,'files':results}
    out={'schema_version':1,'complete':len(common)>=10 and not mismatch and not unreadable,'semantic':semantic,'semantic_sha256':digest_obj(semantic)}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    if not out['complete']: raise SystemExit(f"determinism audit failed: common={len(common)}, mismatch={mismatch}, unreadable={unreadable}")
    return 0
if __name__=='__main__':raise SystemExit(main())
