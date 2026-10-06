from __future__ import annotations
from collections import deque
from itertools import product
from .model import Manifest, event, mode_events, LOCAL_B, LOCAL_N

def local_defects(m: Manifest) -> list[str]:
    out=[]
    for s,f in m.local:
        for a in LOCAL_B:
            if not getattr(f,a): out.append(f"local:{s}:{a}")
        if f.stateful and not f.migrate: out.append(f"local:{s}:migrate")
        # auth and idem already counted above; N-only obligation is refine.
        if not f.refine: out.append(f"local:{s}:refine")
    return sorted(set(out))

def precedence(m: Manifest):
    nodes=[event(k,s) for s in m.services for k in ("B","N")]
    succ={x:set() for x in nodes}; pred={x:set() for x in nodes}
    provenance={}
    def add(a,b,atom):
        succ[a].add(b); pred[b].add(a); provenance.setdefault((a,b),set()).add(atom)
    for s in m.services: add(event("B",s),event("N",s),f"intrinsic:{s}")
    for e in m.edges:
        # Self-edges never expose different source/destination modes under
        # the frozen closure rules, so their directional guards are vacuous.
        if e.caller == e.callee:
            continue
        if not e.n2o: add(event("B",e.callee),event("B",e.caller),f"edge:{e.caller}->{e.callee}:n2o")
        if not e.o2n: add(event("N",e.caller),event("N",e.callee),f"edge:{e.caller}->{e.callee}:o2n")
    return nodes,succ,pred,provenance

def topological_order(m: Manifest):
    nodes,succ,pred,_=precedence(m)
    indeg={x:len(pred[x]) for x in nodes}
    q=deque(sorted(x for x in nodes if indeg[x]==0))
    order=[]
    while q:
        x=q.popleft(); order.append(x)
        for y in sorted(succ[x]):
            indeg[y]-=1
            if indeg[y]==0: q.append(y)
    return order if len(order)==len(nodes) else None

def _shortest_cycle_in_layer(m: Manifest, kind: str):
    # Intrinsic B->N edges cannot belong to a directed cycle because no edge returns N->B.
    verts=list(m.services); adj={v:[] for v in verts}; atom={}
    for e in m.edges:
        if e.caller == e.callee:
            continue
        if kind=="B" and not e.n2o:
            a,b=e.callee,e.caller; at=f"edge:{e.caller}->{e.callee}:n2o"
        elif kind=="N" and not e.o2n:
            a,b=e.caller,e.callee; at=f"edge:{e.caller}->{e.callee}:o2n"
        else: continue
        adj[a].append(b); atom[(a,b)]=at
    best=None
    for start in sorted(verts):
        q=deque([start]); par={start:None}
        found=None
        while q and found is None:
            x=q.popleft()
            for y in sorted(adj[x]):
                if y==start:
                    found=x; break
                if y not in par:
                    par[y]=x; q.append(y)
        if found is not None:
            path=[found]
            while path[-1]!=start: path.append(par[path[-1]])
            path=list(reversed(path))+[start]
            atoms=[atom[(path[i],path[i+1])] for i in range(len(path)-1)]
            candidate=(len(atoms),tuple(atoms),tuple(path),kind)
            if best is None or candidate<best: best=candidate
    return best

def minimum_blocking_witness(m: Manifest) -> dict|None:
    ld=local_defects(m)
    if ld: return {"kind":"local", "atoms":[ld[0]], "minimum_cardinality":1}
    cs=[x for x in (_shortest_cycle_in_layer(m,"B"),_shortest_cycle_in_layer(m,"N")) if x]
    if not cs: return None
    k,atoms,path,layer=min(cs)
    return {"kind":"cycle", "layer":layer, "atoms":list(atoms), "services":list(path), "minimum_cardinality":k}

def _schedule_configs(m: Manifest, order: list[str]):
    modes={s:"O" for s in m.services}; out=[dict(modes)]
    for ev in order:
        k,s=ev.split(":",1)
        modes[s]="B" if k=="B" else "N"
        out.append(dict(modes))
    return out


def strongly_connected_components(m: Manifest):
    nodes,succ,_,_=precedence(m)
    index=0; stack=[]; on=set(); idx={}; low={}; comps=[]
    # Iterative Tarjan: frames retain each DFS successor iterator, separately
    # from the stack of vertices whose SCC has not yet been completed.
    for root in sorted(nodes):
        if root in idx: continue
        idx[root]=low[root]=index; index+=1; stack.append(root); on.add(root)
        frames=[(root,iter(succ[root]))]
        while frames:
            v,children=frames[-1]
            w=next(children,None)
            if w is not None:
                if w not in idx:
                    idx[w]=low[w]=index; index+=1; stack.append(w); on.add(w)
                    frames.append((w,iter(succ[w])))
                elif w in on:
                    low[v]=min(low[v],idx[w])
                continue
            frames.pop()
            if low[v]==idx[v]:
                c=[]
                while True:
                    w=stack.pop();on.remove(w);c.append(w)
                    if w==v:break
                comps.append(tuple(sorted(c)))
            if frames:
                parent=frames[-1][0]
                low[parent]=min(low[parent],low[v])
    return tuple(sorted(comps))

def event_enabled(m: Manifest) -> dict[str,bool]:
    enabled={}
    for s,f in m.local:
        enabled[event("B",s)] = bool(f.bridge and f.auth and f.idem and f.session and (f.migrate or not f.stateful))
        enabled[event("N",s)] = bool(f.refine and f.auth and f.idem)
    return enabled

def compact_frontier_summary(m: Manifest) -> dict:
    nodes,succ,_,_=precedence(m); comps=strongly_connected_components(m)
    cyc=[]
    for c in comps:
        if len(c)>1 or (len(c)==1 and c[0] in succ[c[0]]):cyc.append(c)
    enabled=event_enabled(m)
    mandatory=sorted({x for c in cyc for x in c})
    disabled=sorted(x for x in nodes if not enabled[x])
    target_closed=all(enabled[event("N",s)] for s in m.services)
    return {"target_closed":target_closed,"cyclic_sccs":[list(c) for c in cyc],
            "mandatory_events":mandatory,"disabled_events":disabled,
            "frontier_empty":not target_closed}

def configuration_events(m: Manifest, cfg: dict[str,str]) -> frozenset[str]:
    out=set()
    for s in m.services: out.update(mode_events(s,cfg[s]))
    return frozenset(out)

def frontier_member(m: Manifest, cfg: dict[str,str]) -> bool:
    if not closed(m,cfg): return False
    fs=compact_frontier_summary(m)
    if fs["frontier_empty"]: return False
    done=configuration_events(m,cfg)
    if not all(x in done for x in fs["mandatory_events"]): return False
    # A disabled event may be in the past (e.g., an N configuration after a bridge
    # obligation that is no longer checked), but no incomplete disabled event can
    # be crossed on a future path to all-new.
    if any(x not in done for x in fs["disabled_events"]): return False
    return True

def plan(m: Manifest) -> dict:
    ld=local_defects(m)
    order=None if ld else topological_order(m)
    admitted=order is not None
    cert={"schema":"gateroll.compact-precedence.v1", "manifest_digest":m.digest(),
          "services":list(m.services), "admitted":admitted,
          "frontier_summary":compact_frontier_summary(m)}
    if admitted:
        cert.update({"event_order":order, "witness":None,
                     "complexity":"linear-size event graph; topological decision with canonical sorting"})
    else:
        cert.update({"event_order":None,"witness":minimum_blocking_witness(m),
                     "complexity":"linear-size event graph; all-sources BFS minimum cycle with canonical sorting"})
    return cert

def closed(m: Manifest, cfg: dict[str,str]) -> bool:
    if not isinstance(cfg, dict) or set(cfg) != set(m.services):
        return False
    if any(mode not in ("O", "B", "N") for mode in cfg.values()):
        return False
    lm=m.local_map()
    for s,mode in cfg.items():
        f=lm[s]
        if mode=="B":
            if not (f.bridge and f.auth and f.idem and f.session and (f.migrate or not f.stateful)): return False
        if mode=="N":
            if not (f.refine and f.auth and f.idem): return False
    for e in m.edges:
        a,b=cfg[e.caller],cfg[e.callee]
        if a in {"B","N"} and b=="O" and not e.n2o: return False
        if a in {"O","B"} and b=="N" and not e.o2n: return False
    return True

def explicit_frontier(m: Manifest):
    states=[dict(zip(m.services,x)) for x in product(("O","B","N"), repeat=len(m.services))]
    key=lambda c: tuple(c[s] for s in m.services)
    closed_states={key(c):c for c in states if closed(m,c)}
    target=tuple("N" for _ in m.services)
    if target not in closed_states: return set(),False
    preds={k:[] for k in closed_states}
    for k,c in closed_states.items():
        for i,s in enumerate(m.services):
            if c[s]=="O": nxt="B"
            elif c[s]=="B": nxt="N"
            else: continue
            kk=list(k); kk[i]=nxt; kk=tuple(kk)
            if kk in closed_states: preds[kk].append(k)
    front={target}; q=deque([target])
    while q:
        y=q.popleft()
        for x in preds[y]:
            if x not in front: front.add(x); q.append(x)
    start=tuple("O" for _ in m.services)
    return front, start in front
