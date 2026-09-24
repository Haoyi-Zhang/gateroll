#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, re
from collections import Counter, defaultdict
from pathlib import Path

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s).strip().lower()).strip('_')
def truth(v): return norm(v) in {'1','true','yes','y','ok','pass','passed','available','complete','completed','new','admitted'}
def falsey(v): return norm(v) in {'0','false','no','n','fail','failed','blocked','unavailable','old'}
def num(v):
    try: return float(v)
    except Exception: return None

def read_csv(p):
    with p.open(newline='',errors='replace') as f:
        r=csv.DictReader(f); rows=[]
        for row in r: rows.append({norm(k):v for k,v in row.items() if k is not None})
    return rows

def choose(files,target,required_tokens=()):
    best=None
    for p,rows in files:
        cols=set(rows[0]) if rows else set()
        token_score=sum(any(t in c for c in cols) for t in required_tokens)
        score=(abs(len(rows)-target),-token_score,len(str(p)))
        if best is None or score<best[0]: best=(score,p,rows,cols)
    return best

def col(cols,*aliases):
    for a in aliases:
        if a in cols: return a
    for a in aliases:
        for c in cols:
            if a in c: return c
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); ap.add_argument('--output',type=Path)
    a=ap.parse_args(); root=a.root.resolve(); out=a.output or (Path(__file__).resolve().parent/'reconciled-evidence.json')
    csvs=[]
    for p in root.rglob('*.csv'):
        if 'audit' in p.parts: continue
        try:
            rows=read_csv(p)
            if rows: csvs.append((p,rows))
        except Exception: pass
    if not csvs: raise SystemExit('no CSV evidence files')

    txc=choose(csvs,8640,('campaign','strategy','violation','available'))
    casec=choose(csvs,12000,('planner','checker','oracle','admit'))
    runc=choose(csvs,240,('campaign','strategy','violation','availability'))
    failures=[]; result={'files':{}}

    # Transaction reconciliation
    _,tp,tx,tc=txc; result['files']['transactions']=str(tp.relative_to(root)); result['transactions']=len(tx)
    if len(tx)!=8640: failures.append(f'transaction rows {len(tx)} != 8640')
    campaign=col(tc,'campaign','campaign_id','scenario','scenario_id')
    strategy=col(tc,'strategy','method')
    runid=col(tc,'run_id','strategy_run','execution_id')
    violation=col(tc,'semantic_violation','violation','oracle_violation','semantic_error')
    semantic_ok=col(tc,'semantic_ok','oracle_ok','contract_ok')
    available=col(tc,'available','availability','usable_response')
    keyclass=col(tc,'key_class','affected','partition_class')
    if campaign: result['campaigns']=len({r[campaign] for r in tx})
    if strategy: result['strategies']=sorted({r[strategy] for r in tx}); result['strategy_count']=len(result['strategies'])
    if runid:
        run_counts=Counter(r[runid] for r in tx); result['run_count_from_transactions']=len(run_counts); result['transactions_per_run']=sorted(set(run_counts.values()))
    elif campaign and strategy:
        run_counts=Counter((r[campaign],r[strategy]) for r in tx); result['run_count_from_transactions']=len(run_counts); result['transactions_per_run']=sorted(set(run_counts.values()))
    else: failures.append('cannot identify run key in transaction data')
    def is_viol(r):
        if violation: return truth(r[violation]) or ((num(r[violation]) or 0)>0)
        if semantic_ok: return not truth(r[semantic_ok])
        return False
    if strategy:
        cert=[r for r in tx if 'cert' in norm(r[strategy]) or 'gateroll' in norm(r[strategy])]
        result['certified_transactions']=len(cert); result['certified_violations']=sum(is_viol(r) for r in cert)
    if available and keyclass:
        for label,pred in [('affected',lambda v:'unaffected' not in norm(v) and 'affected' in norm(v)),('unaffected',lambda v:'unaffected' in norm(v))]:
            rs=[r for r in tx if pred(r[keyclass])]
            if rs: result[label+'_availability']=sum(truth(r[available]) for r in rs)/len(rs)

    # Run-level reconciliation
    _,rp,runs,rc=runc; result['files']['runs']=str(rp.relative_to(root)); result['strategy_runs']=len(runs)
    if len(runs)!=240: failures.append(f'run rows {len(runs)} != 240')
    rs=col(rc,'strategy','method'); rv=col(rc,'violations','violation_count','semantic_violations'); rcomplete=col(rc,'final_new','completed_cutover','cutover_complete','final_mode_new')
    if rs:
        cert=[r for r in runs if 'cert' in norm(r[rs]) or 'gateroll' in norm(r[rs])]
        result['certified_runs']=len(cert)
        if rv: result['certified_run_violations']=sum(int(float(r[rv] or 0)) for r in cert)
        if rcomplete: result['certified_completed_cutovers']=sum(truth(r[rcomplete]) for r in cert)

    # Finite-case reconciliation
    _,cp,cases,cc=casec; result['files']['finite_cases']=str(cp.relative_to(root)); result['finite_cases']=len(cases)
    if len(cases)!=12000: failures.append(f'finite-case rows {len(cases)} != 12000')
    planner=col(cc,'planner_admitted','planner','admitted','decision')
    checker=col(cc,'checker_accepted','checker','certificate_valid')
    oracle=col(cc,'oracle_admitted','oracle','schedulable','ground_truth')
    if planner and oracle:
        agree=sum(truth(r[planner])==truth(r[oracle]) for r in cases); result['planner_oracle_agreement']=agree
        result['admitted']=sum(truth(r[oracle]) for r in cases); result['blocked']=len(cases)-result['admitted']
    if checker:
        result['checker_acceptances']=sum(truth(r[checker]) for r in cases)

    # Validate critical invariants; record rather than infer absent optional columns.
    expected={'transactions':8640,'strategy_runs':240,'finite_cases':12000}
    for k,v in expected.items():
        if result.get(k)!=v: failures.append(f'{k}: {result.get(k)} != {v}')
    if result.get('campaigns') not in (None,40): failures.append(f"campaigns: {result.get('campaigns')} != 40")
    if result.get('strategy_count') not in (None,6): failures.append(f"strategy_count: {result.get('strategy_count')} != 6")
    if result.get('run_count_from_transactions') not in (None,240): failures.append(f"run_count_from_transactions: {result.get('run_count_from_transactions')} != 240")
    if result.get('transactions_per_run') not in (None,[36]): failures.append(f"transactions_per_run: {result.get('transactions_per_run')} != [36]")
    if result.get('certified_violations') not in (None,0): failures.append(f"certified_violations: {result.get('certified_violations')} != 0")
    if result.get('certified_run_violations') not in (None,0): failures.append(f"certified_run_violations: {result.get('certified_run_violations')} != 0")
    if result.get('planner_oracle_agreement') not in (None,12000): failures.append(f"planner_oracle_agreement: {result.get('planner_oracle_agreement')} != 12000")
    result['pass']=not failures; result['failures']=failures
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))
    if failures: raise SystemExit(2)
if __name__=='__main__': main()
