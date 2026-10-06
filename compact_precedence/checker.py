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
        if e.caller == e.callee:
            continue
        if not e.n2o:
            a,b=f"B:{e.callee}",f"B:{e.caller}"; adj[a].add(b); atom[(a,b)]=f"edge:{e.caller}->{e.callee}:n2o"
        if not e.o2n:
            a,b=f"N:{e.caller}",f"N:{e.callee}"; adj[a].add(b); atom[(a,b)]=f"edge:{e.caller}->{e.callee}:o2n"
    return nodes,adj,atom

def _acyclic(nodes,adj):
    color={x:0 for x in nodes}
    for root in nodes:
        if color[root]: continue
        color[root]=1; frames=[(root,iter(adj[root]))]
        while frames:
            x,children=frames[-1]
            y=next(children,None)
            if y is None:
                color[x]=2; frames.pop()
            elif color[y]==1:
                return False
            elif color[y]==0:
                color[y]=1; frames.append((y,iter(adj[y])))
    return True

def _witness_blocks(m,w):
    if not isinstance(w, dict) or not isinstance(w.get("atoms"), list) or not w["atoms"]: return False
    if any(not isinstance(a, str) for a in w["atoms"]): return False
    if len(set(w["atoms"])) != len(w["atoms"]): return False
    if w.get("kind")=="local": return len(w["atoms"])==1 and w["atoms"][0] in _local_failures(m)
    if w.get("kind")!="cycle": return False
    nodes,adj,atom=_graph(m)
    path=w.get("services",[]); layer=w.get("layer")
    if not isinstance(path, list) or any(s not in m.services for s in path): return False
    if layer not in ("B", "N") or len(path)<2 or path[0]!=path[-1]: return False
    atoms=[]
    for a,b in zip(path,path[1:]):
        ea,eb=f"{layer}:{a}",f"{layer}:{b}"
        if eb not in adj.get(ea,set()): return False
        atoms.append(atom[(ea,eb)])
    return atoms==w["atoms"] and len(set(path[:-1]))==len(path)-1


def _minimum_blocker_size(nodes, adj, local):
    """Independent all-sources distance check; no planner procedures used."""
    if local:
        return 1
    best = None
    for start in nodes:
        distance = {start: 0}
        pending = deque([start])
        while pending:
            current = pending.popleft()
            for nxt in adj[current]:
                if nxt == start:
                    length = distance[current] + 1
                    best = length if best is None else min(best, length)
                elif nxt not in distance:
                    distance[nxt] = distance[current] + 1
                    pending.append(nxt)
    return best


def _frontier_summary(m, nodes, adj, local):
    # Kosaraju, deliberately different from the planner's Tarjan implementation.
    seen=set();order=[]
    for root in sorted(nodes):
        if root in seen: continue
        seen.add(root); frames=[(root,iter(sorted(adj[root])))]
        while frames:
            x,children=frames[-1]
            y=next(children,None)
            if y is None:
                order.append(x); frames.pop()
            elif y not in seen:
                seen.add(y); frames.append((y,iter(sorted(adj[y]))))
    rev={x:set() for x in nodes}
    for x in nodes:
        for y in adj[x]:rev[y].add(x)
    seen=set();comps=[]
    for root in reversed(order):
        if root in seen: continue
        c=[]; seen.add(root); pending=[root]
        while pending:
            x=pending.pop();c.append(x)
            for y in sorted(rev[x]):
                if y not in seen:
                    seen.add(y);pending.append(y)
        comps.append(tuple(sorted(c)))
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
    if not isinstance(c, dict): return False,"certificate-object"
    if c.get("schema")!="gateroll.compact-precedence.v1": return False,"schema"
    if c.get("manifest_digest")!=m.digest(): return False,"digest"
    if c.get("services")!=list(m.services): return False,"service-order"
    nodes,adj,_=_graph(m); local=_local_failures(m); acyclic=(not local and _acyclic(nodes,adj))
    if c.get("frontier_summary")!=_frontier_summary(m,nodes,adj,local):return False,"frontier-summary"
    if type(c.get("admitted")) is not bool or c["admitted"]!=acyclic:return False,"decision"
    if acyclic:
        order=c.get("event_order")
        if not isinstance(order,list) or any(not isinstance(x, str) for x in order) or sorted(order)!=sorted(nodes):return False,"event-permutation"
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
        witness = c["witness"]
        minimum = _minimum_blocker_size(nodes, adj, local)
        if len(witness["atoms"]) != minimum or type(witness.get("minimum_cardinality")) is not int or witness["minimum_cardinality"] != minimum:
            return False,"witness-minimum"
    return True,"ok"
