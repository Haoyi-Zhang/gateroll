# Conditional runtime refinement argument

## Observable contract

For each authorized request, the campaign oracle observes availability, response shape, protocol success, logical value, authorization outcome, and whether a repeated request identifier applies a second write. A successful response refines the declared contract when its authorization, protocol phase, response shape, value, and effect multiplicity match the oracle state. An unavailable or denied response is not counted as a semantic violation unless it reports a forbidden success; availability is measured separately.

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

The implementation checks some assumptions at the executable boundary—certificate validity, endpoint health metadata, adapter inventory, and migrated record cardinality—but does not prove arbitrary adapter semantics or manifest truthfulness.

## Invariants

During a certified schedule the controller maintains:

- **Frontier invariant:** the advertised mode vector is a state of the accepted certificate path and therefore belongs to the exact frontier.
- **Route invariant:** the proxy rejects an RPC direction forbidden by the current mixed-version edge predicates.
- **Migration-before-publication invariant:** a new stateful endpoint is not published in bridge mode until source state has been dumped, transformed, loaded, and the bounded cardinality check has passed.
- **Receipt invariant:** old and new endpoints receive the same logical request identifier during a dual write; an idempotent endpoint returns the recorded response instead of reapplying the effect.
- **Session invariant:** a declared sticky session is pinned to its selected endpoint until it drains, or translated only when the manifest declares session support.
- **Authorization invariant:** the certified proxy rejects unauthorized writes before forwarding; endpoint metadata must agree with the declared authorization obligation before route changes.
- **Fail-closed invariant:** certificate rejection, missing inventory, authorization mismatch, or incomplete migration leaves or restores old preferred routes.

## Proposition: conditional trace refinement

Under the assumptions above, if the independent checker accepts a certificate and each runtime precondition succeeds, every successful response in the certified execution refines the declared per-request contract; a failed precondition does not publish the offending new route.

**Argument.** Induct on controller actions and requests. Initially only old endpoints are preferred and the initial oracle/state files agree. An `O -> B` action preserves the logical state by the migration assumption and publishes bridge mode only after the load check. Closure supplies all local bridge obligations and both relevant mixed-version edge obligations. An `B -> N` action changes preference but retains the old endpoint for pinned sessions; closure supplies endpoint, authorization, and replay obligations for the new mode. For a request, the route invariant prevents an unsupported edge, the session invariant selects a protocol-compatible endpoint, the authorization invariant prevents forbidden effects, and the receipt invariant makes a repeated identifier observationally equivalent to one effect. Persistent state and journal records re-establish these facts after a modeled process restart. Therefore each successful response matches the oracle transition. If a precondition fails, the controller restores old preferred routes before subsequent traffic, so the unverified route is not published. QED relative to the stated assumptions.

## Executed fault obligations

The 40 campaign scenarios exercise ten fault classes over four topologies. The four pre-cutover inconsistency classes are detected by executable mechanisms rather than by consulting the scenario name as an admission result:

- a missing adapter changes the live inventory, which is compared against the admitted manifest;
- an authorization mismatch changes endpoint health metadata, which fails inventory checking;
- an incomplete migration removes records from the actual transferred state, producing a source/target cardinality mismatch and an abort journal entry;
- a corrupted certificate removes a real frontier member, and the independent checker rejects it.

Crash, delay, reorder, stale route, and duplicate delivery are injected after an otherwise accepted start. The proxy and service processes then determine whether the request succeeds, fails closed, is replayed, or recovers. The `none` class is the ordinary completion control.

## Boundary

The proposition is intentionally weaker than an implementation-level verification theorem. Cardinality detects omissions but not a wrong value-preserving bijection. File replacement is used as an atomic local persistence abstraction; torn writes, machine loss, partitions, concurrent controllers, and cross-service transactions are outside the harness. The measured 36-transaction runs establish bounded counterexample and mechanism evidence, not production availability, throughput, or latency.
