#!/usr/bin/env python3
"""Offline paper and PDF release preflight for the GATEROLL package."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple

from PIL import Image


def run(args: List[str], *, text: bool = True) -> str:
    return subprocess.check_output(args, text=text, stderr=subprocess.STDOUT)  # type: ignore[return-value]


def pdf_info(path: Path) -> Dict[str, str]:
    out = run(["pdfinfo", str(path)])
    d: Dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def first_page_text(path: Path) -> str:
    return run(["pdftotext", "-f", "1", "-l", "1", str(path), "-"])


def classify_pdfs(paper: Path) -> Tuple[Path, Path]:
    rows=[]
    for p in paper.rglob("*.pdf"):
        try:
            text=first_page_text(p)
        except Exception:
            continue
        rows.append((p,text))
    mains=[p for p,t in rows if "GATEROLL" in t and "supplement" not in t.lower()]
    supps=[p for p,t in rows if "supplement" in t.lower()]
    if not mains or not supps:
        raise RuntimeError(f"could not classify PDFs: {[(str(p),t[:80]) for p,t in rows]}")
    return max(mains,key=lambda p:p.stat().st_mtime), max(supps,key=lambda p:p.stat().st_mtime)


def find_reference_page(pdf: Path, pages: int) -> int | None:
    for i in range(1,pages+1):
        text=run(["pdftotext","-f",str(i),"-l",str(i),str(pdf),"-"])
        if re.search(r"(?m)^References\s*$",text):
            return i
    return None


def parse_bib_keys(text: str) -> Set[str]:
    return set(re.findall(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,",text))


def parse_bib_field_entries(text: str, field: str) -> List[str]:
    return [re.sub(r"[{}]","",x).strip().lower() for x in re.findall(r"(?im)^\s*"+re.escape(field)+r"\s*=\s*[\{\"]([^\}\"]+)",text)]


def citation_keys(tex: str) -> Set[str]:
    keys=set()
    for m in re.finditer(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|nocite)\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}",tex):
        for k in m.group(1).split(','):
            if k.strip() and k.strip() != '*': keys.add(k.strip())
    return keys


def font_audit(pdf: Path) -> dict:
    out=run(["pdffonts",str(pdf)])
    lines=[l for l in out.splitlines()[2:] if l.strip()]
    records=[]
    failures=[]
    for line in lines:
        parts=line.split()
        # pdffonts columns: name type encoding emb sub uni object ID
        emb="yes" if "yes" in parts[3:6] else "no"
        rec={"raw":line,"embedded":emb=="yes"}
        records.append(rec)
        if not rec["embedded"]: failures.append(line)
    return {"records":records,"unembedded":failures}


def render_audit(pdf: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True,exist_ok=True)
    prefix=out_dir/"page"
    subprocess.run(["pdftoppm","-png","-r","144",str(pdf),str(prefix)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    pages=[]; failures=[]
    for p in sorted(out_dir.glob("page-*.png")):
        im=Image.open(p).convert("L")
        w,h=im.size
        pix=im.load()
        xs=[]; ys=[]; dark=0
        for y in range(h):
            for x in range(w):
                if pix[x,y] < 245:
                    dark+=1; xs.append(x); ys.append(y)
        bbox=[min(xs),min(ys),max(xs),max(ys)] if xs else None
        edge=False
        if bbox:
            edge=bbox[0] < 8 or bbox[1] < 8 or bbox[2] > w-9 or bbox[3] > h-9
        blank=dark < 1000
        rec={"page":p.name,"width":w,"height":h,"dark_pixels":dark,"content_bbox":bbox,"edge_contact":edge,"blank":blank}
        pages.append(rec)
        if edge or blank: failures.append(rec)
    return {"pages":pages,"failures":failures}


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    root=args.root.resolve(); paper=root/'paper'; artifact=root/'artifact'
    main_pdf,supp_pdf=classify_pdfs(paper)
    main_info=pdf_info(main_pdf); supp_info=pdf_info(supp_pdf)
    main_pages=int(main_info['Pages']); supp_pages=int(supp_info['Pages'])
    ref_page=find_reference_page(main_pdf,main_pages)

    tex_files=list(paper.rglob('*.tex'))
    all_tex='\n'.join(p.read_text(errors='strict') for p in tex_files)
    bib_files=list(paper.rglob('*.bib'))
    if not bib_files: raise RuntimeError('no bibliography source')
    all_bib='\n'.join(p.read_text(errors='strict') for p in bib_files)
    cited=citation_keys(all_tex); bibkeys=parse_bib_keys(all_bib)
    missing=sorted(cited-bibkeys); uncited=sorted(bibkeys-cited)
    dois=[x for x in parse_bib_field_entries(all_bib,'doi') if x]
    titles=[re.sub(r'\W+',' ',x).strip() for x in parse_bib_field_entries(all_bib,'title') if x]
    duplicate_doi=sorted({x for x in dois if dois.count(x)>1})
    duplicate_title=sorted({x for x in titles if titles.count(x)>1})

    subprocess.run(['qpdf','--check',str(main_pdf)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['qpdf','--check',str(supp_pdf)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    main_fonts=font_audit(main_pdf); supp_fonts=font_audit(supp_pdf)
    with tempfile.TemporaryDirectory(prefix='gateroll-paper-audit-') as td:
        td=Path(td)
        main_render=render_audit(main_pdf,td/'main')
        supp_render=render_audit(supp_pdf,td/'supp')

    logs=[]; log_fail=[]
    for p in paper.rglob('*.log'):
        text=p.read_text(errors='ignore')
        flags=[]
        for pat in ('Overfull \\hbox','Overfull \\vbox','undefined references','undefined citations','Citation `'):
            if pat.lower() in text.lower(): flags.append(pat)
        logs.append({"path":str(p.relative_to(root)),"flags":flags})
        if flags: log_fail.append({"path":str(p.relative_to(root)),"flags":flags})

    refs=json.loads((artifact/'audit/reference-metadata-audit.json').read_text())
    template=json.loads((artifact/'audit/template-style-audit.json').read_text())
    visible=run(['pdftotext',str(main_pdf),'-'])+'\n'+run(['pdftotext',str(supp_pdf),'-'])
    privacy_patterns=[r'/mnt/data',r'user-[A-Za-z0-9]',r'file_000000',r'OpenAI',r'ChatGPT']
    privacy_hits=[pat for pat in privacy_patterns if re.search(pat,visible,re.I)]

    author_meta=main_info.get('Author','').strip()
    page_size_ok='612 x 792 pts' in main_info.get('Page size','') and '612 x 792 pts' in supp_info.get('Page size','')
    checks={
        'main_body_12_pages':ref_page==13,
        'main_total_at_least_15_pages':main_pages>=15,
        'supplement_at_least_5_pages':supp_pages>=5,
        'letter_page_size':page_size_ok,
        'at_least_55_references':len(bibkeys)>=55,
        'all_bibliography_entries_cited':not uncited,
        'all_citations_defined':not missing,
        'no_duplicate_doi':not duplicate_doi,
        'no_duplicate_normalized_title':not duplicate_title,
        'reference_metadata_complete':refs.get('complete') is True,
        'all_reference_records_resolved':refs.get('semantic',{}).get('resolved_count')==refs.get('semantic',{}).get('entry_count'),
        'template_style_identical':template.get('complete') is True and all(x.get('identical') for x in template.get('styles',[])),
        'all_main_fonts_embedded':not main_fonts['unembedded'],
        'all_supp_fonts_embedded':not supp_fonts['unembedded'],
        'no_render_blank_or_edge_pages':not main_render['failures'] and not supp_render['failures'],
        'no_log_overflow_or_reference_warning':not log_fail,
        'anonymous_or_empty_pdf_author':author_meta in ('','Anonymous','Anonymous Submission'),
        'no_private_visible_text':not privacy_hits,
    }
    result={
        'schema_version':1,
        'pass':all(checks.values()),
        'checks':checks,
        'main':{'path':str(main_pdf.relative_to(root)),'pages':main_pages,'references_page':ref_page,'sha256':sha256(main_pdf),'metadata':main_info,'fonts':main_fonts,'render':main_render},
        'supplement':{'path':str(supp_pdf.relative_to(root)),'pages':supp_pages,'sha256':sha256(supp_pdf),'metadata':supp_info,'fonts':supp_fonts,'render':supp_render},
        'bibliography':{'entries':len(bibkeys),'cited_keys':len(cited),'missing_keys':missing,'uncited_keys':uncited,'duplicate_doi':duplicate_doi,'duplicate_titles':duplicate_title},
        'logs':logs,
        'privacy_hits':privacy_hits,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    if not result['pass']:
        failed=[k for k,v in checks.items() if not v]
        raise SystemExit('paper release audit failed: '+', '.join(failed))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
