#!/usr/bin/env python3
"""Resolve every bibliography entry against DOI/arXiv/stable publication metadata.

This is a release-time provenance check, not part of the scientific result.  It
uses only metadata endpoints and records enough information to reproduce title
and year comparisons.  Network timestamps and response latency are excluded
from the semantic digest.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

UA = "GATEROLL-reference-metadata-audit/1.0"


def split_entries(text: str) -> List[str]:
    entries=[]
    i=0
    while True:
        m=re.search(r'@[A-Za-z]+\s*\{', text[i:])
        if not m: break
        start=i+m.start(); brace=i+m.end()-1; depth=0; j=brace
        in_quote=False; esc=False
        while j < len(text):
            ch=text[j]
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch=='"': in_quote=not in_quote
            elif not in_quote:
                if ch=='{': depth+=1
                elif ch=='}':
                    depth-=1
                    if depth==0:
                        entries.append(text[start:j+1]); i=j+1; break
            j+=1
        else: raise ValueError("unterminated BibTeX entry")
    return entries


def field(entry: str, name: str) -> str | None:
    # Balanced-brace field parser; quoted values are also supported.
    m=re.search(r'(?im)^\s*'+re.escape(name)+r'\s*=\s*',entry)
    if not m: return None
    i=m.end()
    while i<len(entry) and entry[i].isspace(): i+=1
    if i>=len(entry): return None
    if entry[i]=='{':
        depth=0; j=i
        while j<len(entry):
            if entry[j]=='{': depth+=1
            elif entry[j]=='}':
                depth-=1
                if depth==0: return entry[i+1:j].strip()
            j+=1
    if entry[i]=='"':
        j=i+1; esc=False
        while j<len(entry):
            if esc: esc=False
            elif entry[j]=='\\': esc=True
            elif entry[j]=='"': return entry[i+1:j].strip()
            j+=1
    j=entry.find(',',i)
    return entry[i:(j if j!=-1 else len(entry))].strip()


def parse_bib(path: Path) -> List[dict]:
    text=path.read_text(errors='strict')
    out=[]
    for raw in split_entries(text):
        h=re.match(r'@([A-Za-z]+)\s*\{\s*([^,]+),',raw,re.S)
        if not h: continue
        out.append({
            'entry_type':h.group(1).lower(),
            'key':h.group(2).strip(),
            'title':field(raw,'title') or '',
            'year':field(raw,'year') or '',
            'doi':(field(raw,'doi') or '').strip(),
            'url':(field(raw,'url') or '').strip(),
            'eprint':(field(raw,'eprint') or '').strip(),
            'archiveprefix':(field(raw,'archiveprefix') or '').strip(),
            'booktitle':field(raw,'booktitle') or '',
            'journal':field(raw,'journal') or '',
        })
    return out


def clean_latex(s: str) -> str:
    s=re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\s*', ' ', s)
    s=s.replace('{',' ').replace('}',' ').replace('~',' ')
    s=re.sub(r'\\[&_%#$]', ' ', s)
    return html.unescape(s)


def norm(s: str) -> str:
    s=clean_latex(s).lower()
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return ' '.join(s.split())


def title_scores(a: str, b: str) -> Tuple[float,float]:
    na,nb=norm(a),norm(b)
    ratio=difflib.SequenceMatcher(None,na,nb).ratio()
    sa,sb=set(na.split()),set(nb.split())
    j=len(sa&sb)/len(sa|sb) if sa|sb else 1.0
    return ratio,j


def request_json(url: str, retries: int=3) -> dict:
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            last=e
            time.sleep(0.5*(attempt+1))
    raise last  # type: ignore[misc]


def request_text(url: str, retries: int=3) -> Tuple[int,str,str]:
    last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA})
            with urllib.request.urlopen(req,timeout=30) as r:
                body=r.read(2_000_000).decode('utf-8','replace')
                return int(getattr(r,'status',200)), r.geturl(), body
        except Exception as e:
            last=e
            time.sleep(0.5*(attempt+1))
    raise last  # type: ignore[misc]


def extract_html_title(body: str) -> str:
    for pattern in (
        r'<meta[^>]+name=["\']citation_title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<title[^>]*>(.*?)</title>',
    ):
        m=re.search(pattern,body,re.I|re.S)
        if m: return re.sub(r'<[^>]+>',' ',html.unescape(m.group(1))).strip()
    return ''


def verify_entry(e: dict) -> dict:
    result={k:e[k] for k in ('key','entry_type','title','year','doi','url','eprint')}
    result.update({'resolved':False,'route':None,'remote_title':'','remote_year':'','title_ratio':0.0,'title_jaccard':0.0,'error':None})
    try:
        if e['doi']:
            doi=e['doi'].strip().replace('https://doi.org/','').replace('http://dx.doi.org/','')
            endpoint='https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='')+'/transform/application/vnd.citationstyles.csl+json'
            obj=request_json(endpoint)
            remote_title=obj.get('title') or ''
            if isinstance(remote_title,list): remote_title=' '.join(map(str,remote_title))
            issued=obj.get('issued',{}).get('date-parts',[])
            remote_year=str(issued[0][0]) if issued and issued[0] else str(obj.get('issued',''))
            returned=(obj.get('DOI') or doi).lower()
            result['route']='crossref-doi-csl'
            result['remote_doi']=returned
            result['remote_title']=remote_title
            result['remote_year']=remote_year
            result['resolved']=returned==doi.lower()
        elif e['eprint'] and ('arxiv' in e['archiveprefix'].lower() or re.match(r'^\d{4}\.\d{4,5}',e['eprint'])):
            url='https://export.arxiv.org/api/query?id_list='+urllib.parse.quote(e['eprint'])
            status,final,body=request_text(url)
            m=re.search(r'<entry>.*?<title>(.*?)</title>',body,re.S)
            y=re.search(r'<published>(\d{4})-',body)
            result['route']='arxiv-api'
            result['remote_title']=re.sub(r'\s+',' ',html.unescape(m.group(1))).strip() if m else ''
            result['remote_year']=y.group(1) if y else ''
            result['resolved']=status==200 and bool(m)
            result['resolved_url']=final
        elif e['url']:
            url=e['url'].replace('\\_','_')
            status,final,body=request_text(url)
            result['route']='stable-url'
            result['remote_title']=extract_html_title(body)
            result['resolved']=200 <= status < 400
            result['resolved_url']=final
        else:
            result['error']='no DOI, arXiv identifier, or stable URL'
        if result['remote_title']:
            ratio,j=title_scores(e['title'],result['remote_title'])
            result['title_ratio']=round(ratio,4); result['title_jaccard']=round(j,4)
        result['title_consistent']=bool(result['remote_title']) and (result['title_ratio']>=0.55 or result['title_jaccard']>=0.45)
        # Stable landing pages may have a generic site title; resolution still counts,
        # but title consistency is separately exposed rather than silently assumed.
        result['year_consistent']=True
        if e['year'] and result['remote_year'] and e['year'].isdigit() and result['remote_year'].isdigit():
            result['year_consistent']=abs(int(e['year'])-int(result['remote_year']))<=1
    except Exception as exc:
        result['error']=repr(exc)
    return result


def canonical_digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--bib',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--expected-count',type=int,default=64)
    args=ap.parse_args()
    entries=parse_bib(args.bib)
    seen=set(); duplicates=[]
    for e in entries:
        if e['key'] in seen: duplicates.append(e['key'])
        seen.add(e['key'])
    results=[]
    for i,e in enumerate(entries):
        results.append(verify_entry(e))
        time.sleep(0.08)
    unresolved=[r['key'] for r in results if not r['resolved']]
    title_mismatch=[r['key'] for r in results if r['remote_title'] and not r['title_consistent']]
    year_mismatch=[r['key'] for r in results if not r.get('year_consistent',True)]
    semantic={
        'entry_count':len(entries),
        'expected_count':args.expected_count,
        'duplicate_keys':duplicates,
        'resolved_count':sum(bool(r['resolved']) for r in results),
        'unresolved_keys':unresolved,
        'title_mismatch_keys':title_mismatch,
        'year_mismatch_keys':year_mismatch,
        'entries':results,
    }
    complete=(len(entries)>=args.expected_count and not duplicates and not unresolved and not year_mismatch)
    out={
        'schema_version':1,
        'complete':complete,
        'semantic':semantic,
        'semantic_sha256':canonical_digest(semantic),
        'verified_at_utc':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        'note':'Title mismatches are exposed for human review; stable landing pages may use generic HTML titles.',
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    if not complete:
        raise SystemExit(f"reference audit incomplete: unresolved={unresolved}, year={year_mismatch}, duplicates={duplicates}")
    return 0

if __name__=='__main__':
    raise SystemExit(main())
