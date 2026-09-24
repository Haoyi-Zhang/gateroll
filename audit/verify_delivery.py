#!/usr/bin/env python3
"""Extended release gate for the complete GATEROLL package."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    here=Path(__file__).resolve().parent
    subprocess.run([sys.executable,'-B',str(here/'verify_delivery_base.py'),*sys.argv[1:]],check=True)
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--root',default='.')
    args,_=parser.parse_known_args()
    root=Path(args.root).resolve()
    artifact=root/'artifact' if (root/'artifact').is_dir() else root
    meta=json.loads((artifact/'results/independent-audits/metamorphic-model-audit.json').read_text())
    scale=json.loads((artifact/'results/independent-audits/frontier-scaling-audit.json').read_text())
    refs=json.loads((artifact/'audit/reference-metadata-audit.json').read_text())
    determinism=json.loads((artifact/'audit/reproduction-determinism-audit.json').read_text())
    paper=json.loads((artifact/'audit/paper-release-audit.json').read_text())
    template=json.loads((artifact/'audit/template-style-audit.json').read_text())
    rebuild=json.loads((artifact/'audit/clean-source-rebuild-audit.json').read_text())
    checks={
      'metamorphic_complete':meta.get('complete') is True,
      'metamorphic_assignments':meta.get('semantic',{}).get('exhaustive_two_service_assignments')==16384,
      'metamorphic_seeded_cases':meta.get('semantic',{}).get('random_topology_cases')==768,
      'scale_complete':scale.get('complete') is True,
      'scale_rows':len(scale.get('semantic',{}).get('rows',[]))==33,
      'scale_max_services':scale.get('semantic',{}).get('max_services')==12,
      'references_complete':refs.get('complete') is True,
      'references_at_least_55':refs.get('semantic',{}).get('entry_count',0)>=55,
      'references_all_resolved':refs.get('semantic',{}).get('resolved_count')==refs.get('semantic',{}).get('entry_count'),
      'references_no_duplicate_keys':not refs.get('semantic',{}).get('duplicate_keys'),
      'references_no_year_mismatch':not refs.get('semantic',{}).get('year_mismatch_keys'),
      'reproduction_determinism_complete':determinism.get('complete') is True,
      'paper_release_preflight_pass':paper.get('pass') is True,
      'template_style_unchanged':template.get('complete') is True and all(x.get('identical') for x in template.get('styles',[])),
      'clean_source_rebuild_pixel_match':rebuild.get('pass') is True,
    }
    if not all(checks.values()):
      raise SystemExit('extended delivery gate failed: '+json.dumps(checks,sort_keys=True))
    out={'schema_version':1,'pass':True,'checks':checks}
    target=artifact/'audit/extended-delivery-gate.json'
    target.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps(out,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
