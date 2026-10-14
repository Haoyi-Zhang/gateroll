# Received completions and the same-information control

Endpoint receipts return the original completed increment value, not a new read
of current state. The client oracle therefore keeps current expected state by
target/key separately from received successful increment completions by
target/request ID. Late replay expects the saved value without advancing state.
Request shape, route and delivery delay do not change its effect. A saved ID
with a different effect is an invalid oracle history, refused before forwarding.
An unavailable/invalid reply creates no saved completion. This does not infer
unobserved commits or recover a crashed controller/oracle. Completion records
and their migration are established mechanisms, not novelty; see
[RIFL](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf), Sections 3–4.

## Scientific result locations

`results/completion-oracle/history.json` retains the manifest, ten exact owned
requests, real localhost replies, state expectations, final old/new dumps,
environment and ten-source bindings. Four late replays return 12; later reads
return 13/14. Values and receipts migrate before publication; new preference
and an actual proxy restart retain the original completion. The controller
stays alive. `oracle-pair.json` freshly replays those replies through the exact
incoming oracle, with four false violation labels; it is not another native
service execution. Four original red unit controls all failed, then all passed.

The new `campaign/` files are the complete 240-run rerun: 8,640 transaction rows
and 8,649 workload attempts, with unchanged numerical semantic aggregates and
directly readable requests/replies. `finite/` contains 12,000 fresh literal
inputs, decisions, costs and 96 mutations; `tiny.json` and `compact-audit.json`
are actual fresh checks. The independent RPC/CSV recount also reconstructs
received completions rather than trusting generator hints; four recorded-history
controls failed before that repair and pass afterward. `runtime-recount.json`
rechecks all 8,649 actual matrix attempts. `full-tests.stderr` records the final
81 tests: 80 passed, one optional reference metadata test skipped because its
file is absent. The earlier 77-test log and initial stage bindings are retained.
`campaign/semantic_summary.json`, `timing_summary.json` and `runtime_latency.csv`
are derived from the fresh finite/matrix records, not the historical timing run.
Five `recovery/`
controls and the mechanism-off 12/11 result are local observations, not a crash
theorem. Broad source snapshots are not execution of every listed function.

`results/same-information/finite/` compares an ordinary first-closed-step policy
with reference BFS on the same 12,000 manifests and full certificate output.
`native/` has 80 actual runs, grouped as 40 alternating-order pairs, with the same
certificate/checker/enforcement, 2,880 transactions and every reply. Both policies
build exact frontiers and minimum blockers; none of that work is free. Outputs
tie, including 16 preference cutovers and zero violations per policy. Shared
closure/frontier/blocker/checker/runtime is not independent semantic validation.
This addresses information fairness, not a new graph algorithm or enumeration
advantage over a simple policy.

## Literal measured costs

Current construction + serialization + checking medians are 0.613750 and
0.608700 ms (reference / policy), 1,200 samples each, with reference-first order.
Native lifecycle medians are 2.28404985 and 2.31981065 s; parent CPU medians are
both 0.046875 s; final file-length medians are both 16,575 bytes. These include
certificate work, child startup, migration, workload, fault handling, diagnostic
I/O and cleanup wall, not imports or result packaging. Files include state,
receipts, route/intent files, journals and observation logs. Lengths are logical
final bytes, not allocated blocks or transient peaks. Child CPU/RSS, transient
storage, cold cache, deployment network, power loss and concurrent-authority
costs are unmeasured. No speedup or production cost claim.

## Safe execution entries

From the flat artifact root, use fresh paths strictly below the guarded anchor:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_completion_oracle tests.test_simple_policy -v
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_runtime_recount -v
PYTHONDONTWRITEBYTECODE=1 python -B -m scripts.run_completion_history --artifact-root . --output results/runtime_reproductions/received-completions
PYTHONDONTWRITEBYTECODE=1 python -B -m scripts.run_same_information --artifact-root . --phase finite --output results/runtime_reproductions/policy-finite
PYTHONDONTWRITEBYTECODE=1 python -B -m scripts.run_same_information --artifact-root . --phase native --output results/runtime_reproductions/policy-native
```

Existing directories are refused, never reset. The original base reproduction
does not automatically run the additional history/policy commands. Original
raw/current results, failed compact audit, timings, optional-provenance absence
and Linux receipts remain unchanged and bound to their historical sources.

All native fixtures invoke owned localhost endpoints only. Here native means
actual Python OS processes/TCP/persistent files, not a compiled controller or
production service. Intermediate roles remain annotations; the journal is
diagnostic. Old endpoints are not retired; pending keys may remain unavailable
without retry/peer recovery. Lost-final-reply, controller restart, pin recovery,
multiple authorities and machine/power loss remain outside the guarantee. The
richer client-observational semantics of
[Consistent Updates for Scalable Microservices](https://cs.nyu.edu/~wies/publ/popl26_consistent_updates.pdf)
are not implemented or reproduced by these Boolean/TCP fixtures.
