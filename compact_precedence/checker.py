from __future__ import annotations
from collections import deque
from .model import Manifest, event, LOCAL_B, LOCAL_N

def _local_failures(m):
    out=[]
    for s,f in m.local:
        checks=[("bridge",f.bridge),("auth",f.auth),("idem",f.idem),("session",f.session),("refine",f.refine)]
        if f.stateful: checks.append(("migrate",f.migrate))
        out += [f"local:{s}:{a}" for a,v in checks if not v]
    return sorted(set(out))

def _graph(m):
    nodes=[f"{k}:{s}" for s in m.services for k in ("B","N")]
    adj={x:set() for x in nodes}; atom={}
    for s in m.services: adj[f"B:{s}"].add(f"N:{s}"); atom[(f"B:{s}",f"N:{s}")]=f"intrinsic:{s}"
    for e in m.edges:
        if not e.n2o:
            a,b=f"B:{e.callee}",f"B:{e.caller}"; adj[a].add(b); atom[(a,b)]=f"edge:{e.caller}->{e.callee}:n2o"
        if not e.o2n:
            a,b=f"N:{e.caller}",f"N:{e.callee}"; adj[a].add(b); atom[(a,b)]=f"edge:{e.caller}->{e.callee}:o2n"
    return nodes,adj,atom

def _acyclic(nodes,adj):
    color={x:0 for x in nodes}
    def dfs(x):
        color[x]=1
        for y in adj[x]:
            if color[y]==1:return False
            if color[y]==0 and not dfs(y):return False
        color[x]=2; return True
    return all(color[x] or dfs(x) for x in nodes)

def _witness_blocks(m,w):
    if not w or not w.get("atoms"): return False
    if w.get("kind")=="local": return len(w["atoms"])==1 and w["atoms"][0] in _local_failures(m)
    if w.get("kind")!="cycle": return False
    nodes,adj,atom=_graph(m)
    path=w.get("services",[]); layer=w.get("layer")
    if len(path)<2 or path[0]!=path[-1]: return False
    atoms=[]
    for a,b in zip(path,path[1:]):
        ea,eb=f"{layer}:{a}",f"{layer}:{b}"
        if eb not in adj.get(ea,set()): return False
        atoms.append(atom[(ea,eb)])
    return atoms==w["atoms"] and len(set(path[:-1]))==len(path)-1


def _frontier_summary(m, nodes, adj, local):
    # Kosaraju, deliberately different from the planner's Tarjan implementation.
    seen=set();order=[]
    def d1(x):
        seen.add(x)
        for y in sorted(adj[x]):
            if y not in seen:d1(y)
        order.append(x)
    for x in sorted(nodes):
        if x not in seen:d1(x)
    rev={x:set() for x in nodes}
    for x in nodes:
        for y in adj[x]:rev[y].add(x)
    seen=set();comps=[]
    def d2(x,c):
        seen.add(x);c.append(x)
        for y in sorted(rev[x]):
            if y not in seen:d2(y,c)
    for x in reversed(order):
        if x not in seen:
            c=[];d2(x,c);comps.append(tuple(sorted(c)))
    cyc=sorted(c for c in comps if len(c)>1 or (len(c)==1 and c[0] in adj[c[0]]))
    enabled={}
    for s,f in m.local:
        enabled[f"B:{s}"]=bool(f.bridge and f.auth and f.idem and f.session and (f.migrate or not f.stateful))
        enabled[f"N:{s}"]=bool(f.refine and f.auth and f.idem)
    disabled=sorted(x for x in nodes if not enabled[x])
    target_closed=all(enabled[f"N:{s}"] for s in m.services)
    return {"target_closed":target_closed,"cyclic_sccs":[list(c) for c in cyc],
            "mandatory_events":sorted(x for c in cyc for x in c),
            "disabled_events":disabled,"frontier_empty":not target_closed}

def check_certificate(m: Manifest, c: dict) -> tuple[bool,str]:
    if c.get("schema")!="gateroll.compact-precedence.v1": return False,"schema"
    if c.get("manifest_digest")!=m.digest(): return False,"digest"
    if c.get("services")!=list(m.services): return False,"service-order"
    nodes,adj,_=_graph(m); local=_local_failures(m); acyclic=(not local and _acyclic(nodes,adj))
    if c.get("frontier_summary")!=_frontier_summary(m,nodes,adj,local):return False,"frontier-summary"
    if bool(c.get("admitted"))!=acyclic:return False,"decision"
    if acyclic:
        order=c.get("event_order")
        if not isinstance(order,list) or sorted(order)!=sorted(nodes):return False,"event-permutation"
        pos={x:i for i,x in enumerate(order)}
        if any(pos[a]>=pos[b] for a in nodes for b in adj[a]):return False,"precedence"
        # The concrete mode schedule is derived deterministically from the event order;
        # it is intentionally not duplicated in the compact certificate.
        modes={s:"O" for s in m.services}
        for ev in order:
            k,s=ev.split(":",1); modes[s]="B" if k=="B" else "N"
        if any(v!="N" for v in modes.values()):return False,"schedule-target"
        if c.get("witness") is not None:return False,"spurious-witness"
    else:
        if c.get("event_order") is not None:return False,"blocked-path"
        if not _witness_blocks(m,c.get("witness")):return False,"witness"
    return True,"ok"
