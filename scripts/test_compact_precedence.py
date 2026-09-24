#!/usr/bin/env python3
import copy, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from compact_precedence.model import *
from compact_precedence.planner import *
from compact_precedence.checker import check_certificate

def main():
    local={s:ServiceFacts() for s in ('g','l','s')}
    m=Manifest.build(('g','l','s'),local,[EdgeFacts('g','l',False,True),EdgeFacts('l','s',False,True),EdgeFacts('s','g',False,True)],'cycle')
    c=plan(m); assert not c['admitted']; assert len(c['witness']['atoms'])==3; assert check_certificate(m,c)[0]
    x=copy.deepcopy(c); x['witness']['atoms']=x['witness']['atoms'][:-1]; assert not check_certificate(m,x)[0]
    m2=Manifest.build(('g','l','s'),local,[EdgeFacts('g','l',False,True),EdgeFacts('l','s',True,True)],'dag')
    c2=plan(m2); assert c2['admitted']; assert len(c2['event_order'])==6; assert check_certificate(m2,c2)[0]
    x=copy.deepcopy(c2); x['event_order'][0],x['event_order'][-1]=x['event_order'][-1],x['event_order'][0]; assert not check_certificate(m2,x)[0]
    m3=Manifest.build(('x',),{'x':ServiceFacts(migrate=False)},[],'local'); c3=plan(m3); assert not c3['admitted']; assert c3['witness']['minimum_cardinality']==1
    print('compact precedence tests: PASS')
if __name__=='__main__': main()
