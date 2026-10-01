#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, hashlib, json, re
from pathlib import Path

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s).lower()).strip('_')

def main():
    ap=argparse.ArgumentParser(description='Offline structural, literature, and integrity audit for the GATEROLL delivery.')
    ap.add_argument('--root',type=Path,default=Path.cwd())
    a=ap.parse_args(); root=a.root.resolve(); failures=[]
    main_layout={"README.md", "artifact", "paper"}
    is_main=(root/'paper').is_dir() and (root/'artifact').is_dir()
    art=root/'artifact' if is_main else root
    if is_main:
        got={p.name for p in root.iterdir()}
        if got!=main_layout: failures.append(f'root entries differ: {sorted(got)}')
    audit=art/'audit'
    mf=audit/'FILES.json'
    if not mf.is_file(): failures.append('missing audit/FILES.json')
    else:
        obj=json.loads(mf.read_text())
        for row in obj['files']:
            p=root/row['path'] if is_main else root/row['path']
            if not p.is_file(): failures.append('missing '+row['path']); continue
            if p.stat().st_size!=row['bytes']: failures.append('size '+row['path'])
            if digest(p)!=row['sha256']: failures.append('sha256 '+row['path'])
    paper=root/'paper' if is_main else None
    bibs=(list(paper.glob('*.bib')) if paper else [])+list(art.rglob('*.bib'))
    if not bibs: failures.append('no bibliography')
    else:
        bib=max(bibs,key=lambda p:p.stat().st_size).read_text(errors='replace')
        keys=set(re.findall(r'(?m)^\s*@[A-Za-z]+\s*\{\s*([^,\s]+)',bib))
        tex='\n'.join(p.read_text(errors='replace') for p in paper.glob('*.tex')) if paper else ''
        cited=set()
        for m in re.finditer(r'\\(?:cite|citep|citet|citealp|citeauthor|citeyear|citeyearpar)\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}',tex):
            cited.update(x.strip() for x in m.group(1).split(',') if x.strip())
        if len(keys)<55: failures.append(f'only {len(keys)} bibliography entries')
        if paper and cited-keys: failures.append('missing citation keys '+','.join(sorted(cited-keys)))
        if paper and keys-cited: failures.append('uncited bibliography keys '+','.join(sorted(keys-cited)))
        cands=list(art.rglob('*literature*calibration*.csv'))+list(art.rglob('*reference*calibration*.csv'))
        if not cands: failures.append('literature calibration CSV missing')
        else:
            cal=max(cands,key=lambda p:p.stat().st_size)
            with cal.open(newline='',errors='replace') as f:
                r=csv.DictReader(f); rows=list(r); fields=r.fieldnames or []
            fmap={norm(x):x for x in fields}
            def fcol(*names):
                for n in names:
                    if n in fmap:return fmap[n]
                for n in names:
                    for k,v in fmap.items():
                        if n in k:return v
                return None
            kc=fcol('key','bibkey','citation_key'); dc=fcol('reading_depth','depth','read_depth'); cc=fcol('category','calibration_group','group','track'); nc=fcol('difference','specific_difference','relevance','notes')
            if not all((kc,dc,cc,nc)): failures.append('literature calibration columns incomplete')
            else:
                calkeys={str(x[kc]).strip() for x in rows}; full=[x for x in rows if 'full' in str(x[dc]).lower()]
                if calkeys!=keys: failures.append('literature calibration keys do not equal bibliography keys')
                same=sum(any(t in str(x[cc]).lower() for t in ['same','systems','osdi','nsdi','sosp']) for x in full)
                notable=sum(any(t in str(x[cc]).lower() for t in ['distinguished','award','influential','field_defining','high_visibility','best']) for x in full)
                adjacent=sum('adjacent' in str(x[cc]).lower() for x in full)
                if len(full)<21: failures.append(f'only {len(full)} full-paper readings')
                if same<12: failures.append(f'only {same} same-track full readings')
                if notable<5: failures.append(f'only {notable} notable full readings')
                if adjacent<5: failures.append(f'only {adjacent} adjacent full readings')
                if any(not str(x[nc]).strip() for x in rows): failures.append('empty literature difference note')
    if failures:
        print(json.dumps({'pass':False,'failures':failures},indent=2)); raise SystemExit(1)
    print(json.dumps({'pass':True,'bibliography_entries':len(keys),'full_paper_readings':len(full),'same_track_full':same,'notable_full':notable,'adjacent_full':adjacent},indent=2))
if __name__=='__main__': main()
