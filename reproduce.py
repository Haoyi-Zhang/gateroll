#!/usr/bin/env python3
from __future__ import annotations
import json,pathlib,subprocess,sys,hashlib
ROOT=pathlib.Path(__file__).resolve().parent
BASE=ROOT/'reproduce_base.py'
def output_arg(argv):
    for i,x in enumerate(argv):
        if x=='--output' and i+1<len(argv):return pathlib.Path(argv[i+1]).resolve()
        if x.startswith('--output='):return pathlib.Path(x.split('=',1)[1]).resolve()
    raise SystemExit('reproduce.py requires --output PATH')
def main():
    out=output_arg(sys.argv[1:])
    subprocess.run([sys.executable,'-B',str(BASE),*sys.argv[1:]],check=True,cwd=ROOT)
    out.mkdir(parents=True,exist_ok=True)
    compact=out/'compact-precedence-audit.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/'run_compact_precedence_audit.py'),'--output',str(compact),'--random-cases','12000'],check=True,cwd=ROOT)
    observed=json.loads(compact.read_text()); frozen=json.loads((ROOT/'results'/'compact-precedence-audit.json').read_text())
    compact_match=(observed['semantic_sha256']==frozen['semantic_sha256'] and observed['pass'])
    ph=out/'public-history-verification.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/'verify_public_history.py'),'--root',str(ROOT),'--output',str(ph)],check=True,cwd=ROOT)
    phj=json.loads(ph.read_text())
    summary={'schema':'gateroll.reviewer-hardening-reproduction.v1','base_command_succeeded':True,'compact_precedence_pass':observed['pass'],'compact_semantic_match':compact_match,'compact_semantic_sha256':observed['semantic_sha256'],'public_history_pass':phj['pass'],'complete':bool(compact_match and phj['pass'])}
    (out/'reviewer-hardening-summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    if not summary['complete']: raise SystemExit(1)
if __name__=='__main__':main()
