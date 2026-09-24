# Counterexamples and necessity checks

## Whole-path ordering counterexample

Consider a directed cycle `gateway -> ledger -> store -> gateway`. Each stable old and new deployment may be individually closed. Remove only these mixed-direction atoms:

- new gateway cannot call old ledger;
- new ledger cannot call old store;
- new store cannot call old gateway.

Each missing direction induces a predecessor requirement. Together they form a cycle: ledger must advance before gateway, store before ledger, and gateway before store. No first `O -> B` step is contract-closed, although repairing any one of the three atoms breaks the cycle. The planner therefore returns the three atoms as a minimum-cardinality blocking witness. This is the smallest retained example separating pairwise endpoint validity from rollout-path viability.

## Closure without viability

A configuration may satisfy all currently exposed local and edge obligations yet have no closed monotone continuation to all-new. Such a configuration is closed but excluded from the compatibility frontier. A controller that chooses the first locally valid step can enter this dead end; reverse target reachability removes it before scheduling.

## Dimension necessity in the generated corpus

For every blocked generated case, one dimension is made invisible and the independent forward oracle is rerun. The frozen corpus produces newly false admissions for every dimension: bridge completeness, endpoint refinement, replay idempotence, authorization, session handling, state migration, and directional ordering. These are existence results for the controlled distribution, not estimates of production defect frequency.

## Runtime symptom separation

The transaction oracle distinguishes failures that a single health bit would conflate:

- missing bridge support can make a request unavailable;
- authorization weakening can return a healthy but forbidden success;
- response refinement failure can return a value in the wrong shape;
- partial state migration can return a wrong value after route publication;
- replay failure can apply one logical write twice;
- a session-phase mismatch can report success without satisfying the protocol.

A strategy can therefore have high response availability while violating the semantic contract. Conversely, fail-closed rejection can reduce affected-key availability without a semantic violation. The paper reports these axes separately.
