# GATEROLL artifact

GATEROLL is a bounded research prototype for contract-checked rolling upgrades of stateful RPC service graphs. It combines an exact finite frontier planner, a separately implemented certificate checker, a third reachability oracle, and a local multi-process execution harness.

The artifact supports a deliberately conditional claim: when relevant endpoint, bridge, session, state, authorization, replay, and mixed-direction facts are stated truthfully in the frozen finite manifest, whole-path checking can reject unsafe intermediate deployments that endpoint-only or health-only gates admit. It does not infer those facts from arbitrary programs and does not claim production-scale availability or performance.

## Contents

- `gateroll/`: planner, checker, oracle, corpus generator, proxy, service processes, and campaign controller.
- `inputs/`: eight normalized public interface vocabularies and 24 controlled release-pair specifications. The mutations are experimental; they are not historical upstream releases.
- `tests/`: finite-model, corpus, raw-evidence, and executable-preflight tests.
- `proofs/`: formal definitions, exactness/minimality arguments, runtime assumptions, and counterexamples.
- `results/current/`: fresh Windows-local evidence, readable summaries/core CSVs, and `runtime-evidence.zip` with complete raw records and logs.
- `results/raw/` and `results/summary/`: retained historical evidence and its tables, not the current execution.
- `results/expected/semantic_summary.json`: timing-free expected semantic result used by reproduction.
- `scripts/`: deterministic evaluation, aggregation, verification, and test entry points.
- `claim_evidence_ledger.csv`: mapping from manuscript claims to proofs, code, tests, and raw evidence.
- `literature_calibration.csv`: 64-entry scholarly calibration inventory with 21 full-paper readings, focused supporting verifications, identifiers, manuscript roles, and project-specific deltas.
- `external_resources.csv`: public-interface, scholarly-source, license, and venue-rule inventory.

The implementation uses the Python standard library. It starts only localhost processes and does not contact an external service.

## Current evidence and full reproduction

The real 2026-10-06 Windows-local run completed 40 scenarios × six strategies:
240 runs, 8,640 logical transaction records, and 8,649 workload proxy attempts.
All campaign jobs succeeded on their first attempt with zero job retries or
timeouts. Certified records zero violations, 16/16 expected preference cutovers,
and 24 blocked outcomes. Its mean overall/affected/unaffected availability is
98.1481%/95%/100%; availability includes wrong successes and is separate from
correctness. The semantic aggregates match the retained historical campaign
and frozen expected summary without overwriting either.

`results/current/` is the single current evidence surface. Its
`runtime-evidence.zip` contains the complete fresh result, five dedicated
recovery controls and mechanism-disabled ablation, relative to the project root
(`artifact/results/current/...`). Summaries, core CSVs, recounts, the test log,
the five `controls/*/control.json` files and `ablation/counterexample.json`
remain directly readable.
Unpack into a separate empty directory to inspect every request/reply, state
file, certificate, and log. Original execution paths inside records are retained
unchanged. The old current was moved intact outside this project into workspace
retention; it is not mixed into this archive. Original runs and historical
failures remain untouched. See `results/current/README.md` for source mappings.

The recorded suite has 46 passes and one optional administrative metadata skip;
the current compact audit passes. `reproduction_summary.json` has `complete: true`
for the base scientific pipeline. The top-level `reviewer-hardening-summary.json`
reports `scientific_complete: true`, `release_complete: false`, `complete: false`:
its repaired compact digest differs from the retained failed audit, and the
public-history inputs are unavailable (`pass: null`), not a scientific failure
or an invented provenance pass.

For a new run from the artifact root, choose a nonexistent private output:

```sh
python -B reproduce.py --output results/runtime_reproductions/new-run --workers 4
```

The command runs 12,000 finite cases, the 256-model fragment, the 240-run matrix,
aggregation, semantic comparison, tests, and the compact/history checks. Output
must resolve strictly below `results/runtime_reproductions/` and not already
exist; replacement and pruning are refused. Windows campaigns use `spawn`, at
most four independent parents, and owned Windows Job Object cleanup, not POSIX
fork batches. Job Objects bound owned termination, not CPU or memory use.

The measured campaign duration is 153.389 seconds, and the six-stage base
sequence takes 195.644 seconds. These are instrumented Windows-local durations,
not portable speedups or production performance claims. The earlier 73.9-second
campaign/98.2-second base record remains historical and is not relabeled current.

## Individual checks

For checks over the current raw evidence, first unpack the archive into a
separate empty directory; `FULL_RAW` below denotes its complete
`artifact/results/current/raw/`, not the compact outer CSV subset. Choose
fresh paths for every generated output.

```sh
python -B scripts/run_tests.py --artifact-root . --results FULL_RAW
python -B scripts/run_finite.py --artifact-root . --output /tmp/gateroll-finite
python -B scripts/run_tiny.py --output /tmp/gateroll-tiny.json
python -B scripts/run_campaign_matrix.py \
  --artifact-root . --output results/runtime_reproductions/campaign-new \
  --workers 4 --timeout-seconds 30
```

To recompute claim-facing tables from any complete raw output:

```sh
python -B scripts/aggregate_results.py \
  --raw /tmp/gateroll-raw --output /tmp/gateroll-summary
```

## Evidence dimensions

The finite corpus contains exactly 500 distinct defect assignments for each of 24 controlled release pairs, for 12,000 cases across eight interface families. Every case is decided by the planner, checked by the independent certificate checker, and compared with a separately structured forward reachability oracle.

The runtime matrix contains 40 scenarios: four topologies crossed with ten fault classes. Each scenario runs six strategies, producing 240 strategy runs and 8,640 transaction records. A transaction records availability and semantic observations separately. The four executable pre-cutover inconsistencies—missing adapter, authorization mismatch, partial migration, and corrupted certificate—are detected by live inventory, migrated-state cardinality, or checker behavior rather than by treating the scenario name as an admission result.

The 96 rejected certificate mutations are four payload classes across 24 representatives: admission flips; frontier omissions or empty-frontier insertions; multi-role schedule steps on admitted certificates or spurious schedules on blocked ones; and spurious or additional witness atoms. All 24 witness mutations fail the actually-false-atom check before the deletion-minimality loop. This count does not directly test deletion-minimality rejection; the reference checker enforces deletion minimality, while the planner's increasing-size search establishes minimum cardinality within the false-atom universe.

For authorized requests reported available, unexpected denial, unsuccessful protocol results, wrong shape, and wrong value are oracle violations; unavailability is an availability loss. Available denials of unauthorized writes are expected, and available non-denied responses to them are violations. Availability counts proxy-reported available authorized requests, including unexpected denials and wrong successes. Affected keys `a0`/`a1` and unaffected keys `u0`/`u1` are workload classes: ordinary transfer copies all keys and receipts, whereas the partial-migration fault omits selected affected keys. The `a0` pause is released before serialized transfer.

The designated duplicate/reorder replay compares its result with the current per-target, per-key expectation, not a general per-identifier saved completion value. Its fixed sequence has no intervening same-target/same-key write; it is not evidence about arbitrary later replay responses.

## Interpretation boundaries

- Exactness is relative to the finite Boolean manifest and monotone `O -> B -> N` rollout model.
- Blocking witnesses are minimum-cardinality only within the declared false-atom universe.
- The formal runtime proposition retains truthful manifests/adapters, replica agreement and same-ID resolution before observation as premises. Certified B/N increments now persist a per-key intent before either application. Pending keys block reads and different effects until same-ID/same-effect retries receive two successful equal-value completions; the controller also blocks role migration, preference advancement and old-route reset. Intent survives proxy restart. This implements the local observation barrier, not rollback of a committed half or a general recovery theorem. Cardinality detects omission, not semantic equivalence.
- Five dedicated controls retain real peer failures/post-commit timeouts and explicit persistent crash cuts. Each restarts the proxy while pending; same-ID completion then permits both route reads of 12,12, while unrelated keys remain serviceable. The two crash-cut cases stage their durable cut state before actual restart, rather than observing an instruction-boundary crash; the secondary-timeout case also stages its primary commit. The explicit mechanism-off ablation still returns successful reads 12 then 11. It preserves the prior gap as a negative control, not repaired-default behavior.
- Crashes are injected between logical requests. All four certified delay-tagged requests are guest increments denied before endpoint execution: the certified trace has no service-timeout response or retry and does not exercise post-commit timeout reconciliation. Parallel campaign parents are independent deployments, not concurrent clients within one deployment.
- Recovery requires one proxy and one controller, serialized requests/actions, initial agreement, truthful idempotent endpoints/migration, authentic labels, stable IDs, no bypass writes and atomic same-machine intent/state/receipt persistence. Without same-ID client retry or peer recovery the key stays unavailable. Lost final replies after intent-clear remain ambiguous; there is no exactly-once client acknowledgment, competing-writer synchronization, persistent pin recovery or controller journal replay. General concurrent recovery is not established.
- The local fault model excludes machine loss, Byzantine behavior, torn writes, unrestricted partitions, competing proxies/controllers, and cross-service transactions.
- The public interface families contribute normalized vocabulary only. The release mutations and 36-transaction workloads are controlled research fixtures.
- Baselines are explicit information projections and simple execution strategies, not tuned implementations of named products.

## Evidence and delivery utilities

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

The packet retains `audit/metamorphic_model_audit.py` and
`audit/frontier_scaling_audit.py`, but the current wrapper does not run them.
The first exhaustively checks every one of
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

The compact implementation adds an event-precedence normal form for the frozen Boolean language: all required local facts must hold and the non-self-edge event graph must be acyclic. Self-edge directional guards are vacuous. This is an additional decision implementation; `gateroll/` and the campaign controller still use explicit certificates. A shortest directional cycle is a minimum-cardinality blocker, and the compact checker independently validates that minimum. All closed states of an admitted static manifest have viable continuations, and every complete path has exactly `2n` steps.

Separate compact/provenance entrypoints exist; the current wrapper runs the compact audit and history verifier after the base pipeline, not the compact test entrypoint below. History inputs remain absent. Choose fresh output filenames rather than overwriting the retained failed compact record:

```sh
python3 scripts/test_compact_precedence.py
python3 scripts/run_compact_precedence_audit.py --output results/runtime_reproductions/compact-new.json --random-cases 12000
python3 scripts/verify_public_history.py --root . --output results/runtime_reproductions/history-new.json
```

The original failed audit remains at `results/compact-precedence-audit.json`.
Earlier repaired finite results are separate, under `results/repair_checks/`.
The fresh compact run in `results/current/` also checks 16,384 assignments,
12,000 seeded cases and 27 scale controls, with zero discrepancies;
`reference-compact-differential.json` checks 32,992 models directly against the
original planner and forward oracle, including self-edges, and checks minimum
witness sizes on 884 blocked models. The finite rerun preserves the original
12,000-case classifications and rejects all 96 mutations. No source snapshot,
metadata audit or runtime result is fabricated to complete the wrapper.

From the artifact root, the network-free checks are:

```sh
python -B -m unittest tests.test_model tests.test_repair_model
python -B -m scripts.run_finite --artifact-root . --output results/runtime_reproductions/finite-new --omit-case-corpus
python -B scripts/run_compact_precedence_audit.py --output results/runtime_reproductions/compact-new.json --random-cases 12000
python -B audit/repair_model_audit.py --output results/runtime_reproductions/reference-compact-new.json
```

The current runtime measures all-N preference with old endpoints still live,
serialized transfers, a single-key pause demonstration, and target-only RPC
invocation with annotated-path checks. It implements no session retirement or
controller journal replay. Those distinctions are reflected in the manuscript
and runtime proof premises; the repair does not weaken the existing guards,
receipts, digests, or licenses.
