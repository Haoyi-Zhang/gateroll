# Conditional runtime refinement argument

## Observable contract

The campaign oracle first classifies a request as authorized when it is a read or its caller is a writer or administrator. For an authorized request reported available, an unexpected denial, unsuccessful protocol result, wrong response shape, or wrong logical value is a semantic violation. An unavailable authorized request is an availability loss, not a semantic violation. For an unauthorized write, an available denial is expected; any available response without a denial is a violation. Unavailability is not labeled a semantic violation in either branch. Availability is the proxy-reported available fraction of authorized requests, so it includes available unexpected denials and wrong successes rather than measuring usable or correct responses.

The expected logical value advances only after an authorized, nonduplicate increment returns an available response without a violation. The designated duplicate does not advance it again; the oracle compares that response with the current per-target, per-key expectation. It does not maintain a general saved completion value for every identifier. The fixed replay sequence has no intervening write to that target/key between the designated request and its replay; arbitrary later replays are outside this oracle's demonstrated scope.

## Runtime assumptions

The argument below assumes:

1. the finite manifest truthfully summarizes the executed endpoints and adapters;
2. a migration adapter is deterministic and preserves the declared logical state for every migrated record;
3. persistent state files and request receipts survive process restart on the same machine;
4. the proxy and controller are the only route and rollout authorities;
5. request identifiers are unique per logical effect and remain stable across retries and dual writes;
6. authorization labels and session identifiers supplied to the proxy are authentic;
7. crashes are crash-stop/restart events, not Byzantine behavior or loss of the machine containing both state and journal;
8. the finite service graph and fault schedule remain within the declared bounds.
9. migration is serialized with workload requests, replicas agree before a successful observation, and a partially applied dual write is resolved with the same identifier before another observation on that key.

The implementation checks some assumptions at the executable boundary—certificate validity, endpoint health metadata, adapter inventory, and migrated record cardinality—but does not prove arbitrary adapter semantics or manifest truthfulness.

## Invariants

During a certified schedule the controller maintains:

- **Frontier invariant:** the advertised mode vector is a state of the accepted certificate path and therefore belongs to the exact frontier.
- **Route invariant:** the proxy rejects an RPC direction forbidden by the current mixed-version edge predicates.
- **Migration-before-publication invariant:** a new stateful endpoint is not published in bridge mode until source state has been dumped, transformed, loaded, and the bounded cardinality check has passed.
- **Receipt invariant:** old and new endpoints receive the same logical request identifier during a dual write; an idempotent endpoint returns the recorded response instead of reapplying the effect.
- **Session invariant:** the campaign's sticky session remains pinned to its selected endpoint. The implementation does not drain pins or retire old endpoints before terminal traffic.
- **Authorization invariant:** the certified proxy rejects unauthorized writes before forwarding; endpoint metadata must agree with the declared authorization obligation before route changes.
- **Fail-closed invariant:** certificate rejection, missing inventory, authorization mismatch, or incomplete migration leaves or restores old preferred routes.

## Proposition: conditional trace refinement

Under the assumptions above, accepted actions and serialized completed requests preserve the declared per-target contract; a failed executable preflight does not publish the offending new route. Replica synchronization after a partial write is an additional premise, not a consequence of the Boolean manifest, local receipts, or the journal. The unconditional extension to arbitrary interrupted/concurrent dual writes is not established.

**Argument.** Induct on serialized controller actions and completed requests. Initially old endpoints and oracle state agree. An `O -> B` action transfers logical values and receipts without interleaved workload requests and publishes only after the count check. An `B -> N` action changes preference but retains the old endpoint for pins. The path guard checks declared modes along an annotated path; the harness actually invokes only its target, not intermediate services. The session and authorization guards restrict target selection and effects. A completed dual write preserves replica agreement; an idempotent retry returns its recorded completion rather than applying a second effect. Local persistence retains these records after a same-implementation process restart. This induction requires the synchronization premise after a partial write and does not derive it from receipts. If a preflight fails, the explicit controller branch leaves or restores old preferred routes. The journal records observations; it is not replayed to recover a crashed controller. QED for this restricted fragment under the stated premises.

## Local implementation of the synchronization premise

For the single-proxy/single-controller serialized B/N increment fragment, the current implementation makes assumption 9 operational with a durable per-target/key intent written before either endpoint call. The proxy request lock serializes intent changes; while pending, workload reads and different-ID/effect writes on that key are refused, and the controller guards migration, preference advancement and old-route reset for its role. A same-ID, same-effect retry replays a surviving receipt on a committed endpoint and applies once on a missing endpoint; the intent is cleared only after two successful write replies with equal logical values. A timeout, error, disagreement or failed clear retains the barrier. Under initial agreement, truthful idempotent endpoints/migration, authentic labels, unique stable IDs, no bypass writes, serialized controller actions and atomic same-machine intent/state/receipt survival, a crash before clear leaves a replayable fence and a crash after clear leaves two committed replicas. This is a local implementation argument for excluding unreconciled successful observations, not a new general recovery or concurrency theorem. The lock does not synchronize a competing controller/proxy. Without client retry or endpoint recovery, safety can mean indefinite key unavailability; losing the final reply after clear still leaves ambiguous client completion, and the received-completion oracle does not verify arbitrary such histories.

## Executed fault obligations

The 40 campaign scenarios exercise ten fault classes over four topologies. The four pre-cutover inconsistency classes are detected by executable mechanisms rather than by consulting the scenario name as an admission result:

- a missing adapter changes the live inventory, which is compared against the admitted manifest;
- an authorization mismatch changes endpoint health metadata, which fails inventory checking;
- an incomplete migration removes records from the actual transferred state, producing a source/target cardinality mismatch and an abort journal entry;
- a corrupted certificate removes a real frontier member, and the independent checker rejects it.

Crashes occur between logical requests. All four certified delay-tagged requests are guest increments denied by the authorization guard before endpoint execution; the certified trace contains no service-timeout response or retry, so this class does not test post-commit timeout reconciliation. The named `reorder` and `duplicate` scenarios both resend the same saved request; they are not distinct asynchronous scheduling experiments. Process restart waits for a successful health response but does not repeat the full inventory preflight. The `none` class is the ordinary completion control.

The fresh serialized campaign does not test recovery of an interrupted dual write. Its response-level recount covers 8,649 workload proxy attempts without label or availability discrepancies; at 324 certified B/N target snapshots, including 244 after successful replies, values and receipt-ID sets agree. This is bounded post-reply evidence, not a check of receipt contents, arbitrary intermediate states, or concurrent safety.

The five actual controls in `results/current/controls/` cover a failed secondary, primary and secondary post-commit timeouts, an intent-only cut, and a both-committed-before-clear cut. Each kills/restarts its owned proxy while pending and retains the intent. Both route reads, new-ID/changed-effect writes and three controller actions remain blocked; unrelated `u0` reads return 13. Same-ID completion clears pending and both routes then read 12,12; completed-ID replay changes neither state nor receipt set. The intent-only and both-committed cases explicitly construct persistent cuts and then restart the real proxy, with `partial_response: null`, not an invented observed failure reply. The secondary-timeout case also labels a staged primary-commit cut. This is bounded mechanism evidence, separate from the ordinary 40×6 regression matrix.

The actual `results/current/ablation/counterexample.json` explicitly disables pending recovery (`pending_dual_write_enabled: false`) and reproduces the prior unavailable write, physical 12/11 split and successful reads 12 then 11. It identifies the earlier missing synchronization mechanism; narrowing a proposition alone was not an implementation repair. This is not repaired-default behavior or a counterexample under assumption 9. The old control and prior full result remain outside canonical current, and their original workspace outputs are untouched.

## Boundary

The proposition is intentionally weaker than an implementation-level verification theorem. Cardinality detects omissions but not a wrong value-preserving bijection. The first bridge-entry pause is a single unavailable request on `a0`, released before transfer; serialization, not a concurrent partition drain, prevents writes during migration. All-N means all new endpoints are preferred; old endpoints and pins remain until teardown. File replacement is an atomic local persistence abstraction; torn writes, machine loss, partitions, controller crash/recovery, persistent session-pin recovery, O-mode uncertain writes, lost-final-reply histories, competing writers and cross-service transactions are outside the established argument. Diagnostic dumps may expose a physical split while pending; they are not successful workload observations. Retained runs are bounded mechanism evidence, not production availability, throughput, or latency. Availability counts proxy-reported availability even for wrong successes and must be interpreted separately from correctness.
