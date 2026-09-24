#!/usr/bin/env python3
from __future__ import annotations
import argparse, itertools, json, random, statistics, time, hashlib, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from compact_precedence.model import Manifest, ServiceFacts, EdgeFacts
from compact_precedence.planner import plan, explicit_frontier, minimum_blocking_witness, frontier_member
from compact_precedence.checker import check_certificate

ATOMS=("a.refine","a.bridge","a.migrate","a.auth","a.idem","a.session",
       "b.refine","b.bridge","b.migrate","b.auth","b.idem","b.session","a-b.n2o","a-b.o2n")
def m2(bits):
    d=dict(zip(ATOMS,bits))
    local={s:ServiceFacts(refine=d[f"{s}.refine"],bridge=d[f"{s}.bridge"],migrate=d[f"{s}.migrate"],auth=d[f"{s}.auth"],idem=d[f"{s}.idem"],session=d[f"{s}.session"],stateful=True) for s in ("a","b")}
    return Manifest.build(("a","b"),local,[EdgeFacts("a","b",d["a-b.n2o"],d["a-b.o2n"])],"exhaustive")
def random_manifest(rng,n,i):
    ss=tuple(f"s{x}" for x in range(n)); local={s:ServiceFacts(**{k:(rng.random()>0.08) for k in ("refine","bridge","migrate","auth","idem","session")},stateful=True) for s in ss}
    edges=[]
    for a in ss:
        for b in ss:
            if a!=b and rng.random()<min(.28,2.5/n): edges.append(EdgeFacts(a,b,rng.random()>.22,rng.random()>.22))
    return Manifest.build(ss,local,edges,f"rnd-{n}-{i}")
def repaired(n,kind):
    ss=tuple(f"s{x}" for x in range(n)); local={s:ServiceFacts() for s in ss}; edges=[]
    if kind=="chain": edges=[EdgeFacts(ss[i],ss[i+1]) for i in range(n-1)]
    elif kind=="ring": edges=[EdgeFacts(ss[i],ss[(i+1)%n],False,True) for i in range(n)]
    elif kind=="reverse-ring": edges=[EdgeFacts(ss[i],ss[(i+1)%n],True,False) for i in range(n)]
    return Manifest.build(ss,local,edges,f"scale-{kind}-{n}")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',required=True); ap.add_argument('--random-cases',type=int,default=12000); args=ap.parse_args()
    out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    t0=time.perf_counter(); mism=checkfail=witfail=membership_mismatch=0; admitted=0
    for mask in range(1<<len(ATOMS)):
        bits=tuple(bool(mask&(1<<i)) for i in range(len(ATOMS))); m=m2(bits); c=plan(m); front,oracle=explicit_frontier(m)
        admitted+=int(c['admitted'])
        if c['admitted']!=oracle:mism+=1
        for a in ("O","B","N"):
            for b in ("O","B","N"):
                cfg={"a":a,"b":b}; membership_mismatch += (tuple((a,b)) in front) != frontier_member(m,cfg)
        ok,_=check_certificate(m,c); checkfail+=not ok
        if not c['admitted'] and c['witness'] is None:witfail+=1
    exhaustive_seconds=time.perf_counter()-t0
    rng=random.Random(20260920); random_mismatch=random_check=permutation_fail=repair_fail=0; sizes={}
    random_membership_mismatch=0
    t1=time.perf_counter()
    for i in range(args.random_cases):
        n=3+(i%10); m=random_manifest(rng,n,i); c=plan(m); ok,_=check_certificate(m,c); random_check+=not ok
        if n<=7:
            front,oracle=explicit_frontier(m); random_mismatch += c['admitted']!=oracle
            from itertools import product
            for modes in product(("O","B","N"),repeat=n):
                cfg=dict(zip(m.services,modes)); random_membership_mismatch += (modes in front) != frontier_member(m,cfg)
        # Renaming invariance.
        perm=list(m.services); rng.shuffle(perm); mp=dict(zip(m.services,perm))
        lm={mp[s]:f for s,f in m.local}; es=[EdgeFacts(mp[e.caller],mp[e.callee],e.n2o,e.o2n) for e in m.edges]
        mr=Manifest.build(tuple(perm),lm,es,m.identity+'-renamed')
        permutation_fail += plan(mr)['admitted']!=c['admitted']
        # Repair monotonicity: replacing all facts by true cannot turn an admitted instance into blocked.
        fixed=Manifest.build(m.services,{s:ServiceFacts(stateful=f.stateful) for s,f in m.local},[EdgeFacts(e.caller,e.callee,True,True) for e in m.edges],m.identity+'-fixed')
        repair_fail += c['admitted'] and not plan(fixed)['admitted']
        sizes[n]=sizes.get(n,0)+1
    random_seconds=time.perf_counter()-t1
    scale=[]
    for n in (8,12,16,24,32,48,64,96,128):
        for kind in ("chain","ring","reverse-ring"):
            m=repaired(n,kind); a=time.perf_counter(); c=plan(m); dt=time.perf_counter()-a; ok,_=check_certificate(m,c)
            scale.append({"services":n,"shape":kind,"admitted":c['admitted'],"witness_size":0 if c['witness'] is None else len(c['witness']['atoms']),"seconds":dt,"checker":ok,"certificate_bytes":len(json.dumps(c,separators=(',',':')))})
    semantic={"schema":"gateroll.compact-precedence-audit.v1","exhaustive_assignments":1<<len(ATOMS),"exhaustive_admitted":admitted,"exhaustive_decision_mismatches":mism,"exhaustive_frontier_membership_mismatches":membership_mismatch,"exhaustive_checker_failures":checkfail,"exhaustive_missing_witnesses":witfail,"random_cases":args.random_cases,"random_explicit_oracle_cases":sum(v for k,v in sizes.items() if k<=7),"random_decision_mismatches":random_mismatch,"random_frontier_membership_mismatches":random_membership_mismatch,"random_checker_failures":random_check,"permutation_failures":permutation_fail,"repair_monotonicity_failures":repair_fail,"scale_semantics":[{k:v for k,v in x.items() if k!='seconds'} for x in scale]}
    digest=hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result={"semantic":semantic,"semantic_sha256":digest,"measurements":{"exhaustive_seconds":exhaustive_seconds,"random_seconds":random_seconds,"scale":scale},"pass":all(x==0 for x in (mism,membership_mismatch,checkfail,witfail,random_mismatch,random_membership_mismatch,random_check,permutation_fail,repair_fail)) and all(x['checker'] for x in scale)}
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    if not result['pass']: raise SystemExit(1)
if __name__=='__main__': main()
