# Final Artifact Audit

This audit was generated from a clean extraction of the delivered archives. It is an internal consistency check, not independent peer review.

## Publication

- Bibliography entries: **64**.
- Distinct citation keys used by the paper sources: **64**.
- Missing citation keys: **0**.
- Uncited bibliography entries: **0**.
- Main PDF pages: **15**.
- Supplementary PDF pages: **3**.
- The build completed without detected overfull boxes, undefined references, undefined citations, or LaTeX errors.
- All reported PDF fonts are embedded and identity/path residue checks passed.

## Reproduction

A clean standalone extraction ran `python3 -B reproduce.py --output <empty-directory>`. The generated evidence contains a status object with `complete: true` and `semantic_match: true`, and exposes the required 12,000 finite cases, 40 campaigns, 240 strategy executions, and 8,640 transaction records. The command returned without a Python traceback.

## Integrity and structure

The main archive has one root whose direct entries are exactly `paper/`, `artifact/`, `research-plan.md`, and `CURRENT-STATE.md`. `FILES.json` records SHA-256 digests and byte sizes for every retained file except itself. Run:

```sh
python3 artifact/audit/verify_delivery.py --root .
```

The verifier checks root structure, recorded hashes, the 55-reference minimum, citation closure, and the absence of unused bibliography entries.

## Claim boundary

The evidence validates the implemented finite manifest semantics and the controlled local runtime campaigns. It does not establish the truth of an incorrectly supplied manifest, whole-program equivalence, fleet-scale performance, resilience to machine loss or Byzantine behavior, or production defect prevalence.
