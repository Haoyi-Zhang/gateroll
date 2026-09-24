# GATEROLL artifact

GATEROLL is a bounded research prototype for contract-checked rolling upgrades of stateful RPC service graphs. It combines an exact finite frontier planner, a separately implemented certificate checker, a third reachability oracle, and a local multi-process execution harness.

The artifact supports a deliberately conditional claim: when relevant endpoint, bridge, session, state, authorization, replay, and mixed-direction facts are stated truthfully in the frozen finite manifest, whole-path checking can reject unsafe intermediate deployments that endpoint-only or health-only gates admit. It does not infer those facts from arbitrary programs and does not claim production-scale availability or performance.

## Contents

- `gateroll/`: planner, checker, oracle, corpus generator, proxy, service processes, and campaign controller.
- `inputs/`: eight normalized public interface vocabularies and 24 controlled release-pair specifications. The mutations are experimental; they are not historical upstream releases.
- `tests/`: finite-model, corpus, raw-evidence, and executable-preflight tests.
- `proofs/`: formal definitions, exactness/minimality arguments, runtime assumptions, and counterexamples.
- `results/raw/`: retained claim-critical outputs from the frozen run.
- `results/summary/`: tables derived from raw records.
- `results/expected/semantic_summary.json`: timing-free expected semantic result used by reproduction.
- `scripts/`: deterministic evaluation, aggregation, verification, and test entry points.
- `claim_evidence_ledger.csv`: mapping from manuscript claims to proofs, code, tests, and raw evidence.
- `literature_calibration.csv`: 64-entry scholarly calibration inventory with 21 full-paper readings, focused supporting verifications, identifiers, manuscript roles, and project-specific deltas.
- `external_resources.csv`: public-interface, scholarly-source, license, and venue-rule inventory.

The implementation uses the Python standard library. It starts only localhost processes and does not contact an external service.

## Full reproduction

Run from a clean artifact directory:

```sh
python -B reproduce.py --output ../reproduced
```

The default command runs the complete 12,000-case finite evaluation, the 256-model exhaustive fragment, all 40 campaigns under six strategies, aggregation, semantic comparison, and the test suite. Up to four campaign jobs run concurrently. The matrix is divided into fresh two-campaign process batches so that descriptor and child-process cleanup cannot accumulate across the full run. On the retained clean run, the finite stage took 19.9 seconds, the 240-strategy campaign matrix 73.9 seconds, and the complete command 98.2 seconds; local timing is environment-specific.

The output directory must not already exist unless `--replace` is supplied. A successful run ends with `complete: true` in `reproduction_summary.json` and `semantic_match: true` in `verification_report.json`.

## Individual checks

```sh
python -B scripts/run_tests.py --artifact-root . --results results/raw
python -B scripts/run_finite.py --artifact-root . --output /tmp/gateroll-finite
python -B scripts/run_tiny.py --output /tmp/gateroll-tiny.json
python -B scripts/run_campaign_matrix.py \
  --artifact-root . --output /tmp/gateroll-campaigns \
  --workers 4 --timeout-seconds 30 --prune-runs
```

To recompute claim-facing tables from any complete raw output:

```sh
python -B scripts/aggregate_results.py \
  --raw /tmp/gateroll-raw --output /tmp/gateroll-summary
```

## Frozen evidence dimensions

The finite corpus contains exactly 500 distinct defect assignments for each of 24 controlled release pairs, for 12,000 cases across eight interface families. Every case is decided by the planner, checked by the independent certificate checker, and compared with a separately structured forward reachability oracle.

The runtime matrix contains 40 scenarios: four topologies crossed with ten fault classes. Each scenario runs six strategies, producing 240 strategy runs and 8,640 transaction records. A transaction records availability and semantic observations separately. The four executable pre-cutover inconsistencies—missing adapter, authorization mismatch, partial migration, and corrupted certificate—are detected by live inventory, migrated-state cardinality, or checker behavior rather than by treating the scenario name as an admission result.

## Interpretation boundaries

- Exactness is relative to the finite Boolean manifest and monotone `O -> B -> N` rollout model.
- Blocking witnesses are minimum-cardinality only within the declared false-atom universe.
- The runtime argument assumes truthful manifests and semantically correct adapters. Cardinality checking detects omission, not an incorrect value-preserving transform.
- The local fault model excludes machine loss, Byzantine behavior, torn writes, unrestricted partitions, concurrent controllers, and cross-service transactions.
- The public interface families contribute normalized vocabulary only. The release mutations and 36-transaction workloads are controlled research fixtures.
- Baselines are explicit information projections and simple execution strategies, not tuned implementations of named products.

## Final integrity and evidence audit

After the normal reproduction, the following commands perform checks that do
not import the planner, checker, proxy, controller, or paper aggregation code:

```sh
python3 audit/reconcile_evidence.py --root . --output audit/reconciled-evidence.json
python3 audit/verify_delivery.py --root ..
```

`reconcile_evidence.py` independently recounts the finite cases, run records,
and transaction records.  `verify_delivery.py` checks archive shape, retained
SHA-256 hashes, and citation closure.  These are delivery and accounting
checks, not independent peer review or a proof that the manifest is truthful.

## Independent semantic audits

The complete entry point also runs `audit/metamorphic_model_audit.py` and
`audit/frontier_scaling_audit.py`.  The first exhaustively checks every one of
16,384 assignments in a 14-atom two-service model and 768 deterministic larger
topologies using two separately structured decision procedures plus
metamorphic properties.  The second executes exact enumeration for three
structural families through twelve service roles.  Frozen, time-insensitive
results are in `results/independent-audits/`; reproduced results and digest
comparisons are written beneath the requested output directory.

## Release-integrity audits

The frozen release also includes `audit/reference_metadata_audit.py`,
`audit/reproduction_determinism_audit.py`, and `audit/paper_release_audit.py`.
The first resolves every bibliography record through DOI, arXiv, or a stable
publication URL and records the returned metadata.  The second compares two
clean reproductions after deleting only measurement-specific fields.  The third
checks citation closure, template identity, page boundaries, fonts, build logs,
anonymity-sensitive text, and raster page margins.  These are release checks,
not additional production-system claims.



## Compact-precedence hardening

The final hardening round adds an exact event-precedence normal form for the frozen Boolean language. Admission no longer requires explicit enumeration of all `3^n` deployment configurations: the planner checks required local facts and topologically sorts two events per service. A shortest directed cycle is a minimum-cardinality directional blocker. The independent checker uses a separately implemented graph construction and cycle/order validation.

Reproduction now also runs:

```sh
python3 scripts/test_compact_precedence.py
python3 scripts/run_compact_precedence_audit.py --output results/compact-precedence-audit.json --random-cases 12000
python3 scripts/verify_public_history.py --root . --output results/public-history-verification.json
```

The compact audit exhausts all 16,384 assignments of the two-service 14-atom language, cross-checks deterministic larger cases, applies metamorphic tests, and exercises certificates through 128 roles. A separate tagged public-schema probe retains exact upstream snapshots and hashes, but is explicitly syntax-only and is not counted as a historical runtime evaluation.
