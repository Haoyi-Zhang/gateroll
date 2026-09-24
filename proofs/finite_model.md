# Finite contract model and proof obligations

## Scope

The results in this note concern one finite rollout manifest. The manifest is trusted input: it declares a finite directed service graph, one old endpoint and one candidate new endpoint per service, local compatibility predicates, and mixed-version edge predicates. The algorithms do not inspect arbitrary program bodies or infer these predicates.

## Definitions

Let a manifest be `M = (S, E, P, Q)`, where `S` is an ordered finite set of service roles, `E` is a directed RPC edge set, `P` contains local Boolean obligations, and `Q` contains directional mixed-version obligations. A deployment configuration is a function `c : S -> {O, B, N}`:

- `O` exposes only the old endpoint;
- `B` exposes both endpoints through the declared bridge;
- `N` prefers the new endpoint while the old endpoint may remain only for bounded draining during the corresponding runtime step.

For each service `s`, the manifest declares endpoint refinement, bridge completeness, state-migration totality when stateful, authorization refinement, replay idempotence, and session drain/translation. For each directed edge `(u,v)`, it declares support for new-or-bridge `u` calling old `v` (`n2o`) and old-or-bridge `u` calling new `v` (`o2n`).

`Closed_M(c)` holds exactly when:

1. if `c(s)=B`, bridge, authorization, replay, and session obligations hold, and migration holds when `s` is stateful;
2. if `c(s)=N`, endpoint refinement, authorization, and replay obligations hold;
3. if `c(u) in {B,N}` and `c(v)=O`, `n2o(u,v)` holds;
4. if `c(u) in {O,B}` and `c(v)=N`, `o2n(u,v)` holds.

A rollout edge advances exactly one role by one step in `O -> B -> N`. Let `C_M` be all closed configurations and `t=N^|S|`. The compatibility frontier is

`F_M = { c in C_M | c ->* t using only configurations in C_M }`.

A manifest is admitted exactly when `O^|S|` is in `F_M`.

## Theorem 1: frontier exactness and maximality

The planner enumerates all `3^|S|` configurations, retains exactly those satisfying `Closed_M`, constructs the one-role monotone transition relation restricted to retained configurations, and performs reverse reachability from `t`. The returned set equals `F_M`.

**Proof.** Enumeration is complete because every configuration is one tuple in `{O,B,N}^|S|`. The closure predicate is evaluated by direct application of the four rules, so the retained vertex set is exactly `C_M`. Successor and predecessor construction changes one coordinate by one and therefore equals the rollout transition relation. Reverse reachability includes a retained configuration iff a finite path of retained transitions reaches `t`, which is the definition of membership in `F_M`. Any viable subset of `C_M` whose vertices can reach `t` is therefore contained in `F_M`; hence `F_M` is the unique maximal viable subset. QED.

The implementation cost is `O(3^|S| (|S|+|E|))` time and `O(3^|S|)` configurations, excluding witness minimization. The evaluated service graphs have at most five roles and 243 configurations.

## Theorem 2: admitted certificate soundness relative to the manifest

If the independent checker accepts an admitted certificate, the supplied path begins at all-old, ends at all-new, changes exactly one role by one mode at each step, and every path state belongs to the exact compatibility frontier.

**Proof.** The checker independently reconstructs closure and reverse reachability using integer base-three states. It requires set equality between the reconstructed frontier and the certificate frontier, checks the admission bit against all-old membership, checks path endpoints, and checks every step difference. Frontier membership implies closure and target reachability by Theorem 1. No planner decision bit is trusted without reconstruction. QED.

This theorem is conditional on the truth of manifest predicates; it is not a proof of arbitrary endpoint implementations or adapter code.

## Theorem 3: blocking-witness minimality in the declared defect universe

Let `D` be all false atoms in the supplied manifest. The planner repairs all atoms, enumerates subsets of `D` by increasing cardinality, and returns the first subset `W` whose reapplication blocks all-old. Then `W` is minimum-cardinality among subsets of `D` that block the repaired manifest, and therefore deletion-minimal.

**Proof.** Every subset of size smaller than `|W|` is tested before `W` and found schedulable. Thus no smaller blocking subset exists. Deleting one atom yields a smaller subset and is therefore schedulable. QED.

The checker does not trust the planner's search: it reconstructs the repaired manifest, reapplies `W`, checks blocking, then checks schedulability after every one-atom deletion. The claim is only about the declared false-atom universe. It is not a minimum source-code explanation or a shortest failing execution.

## Theorem 4: shortest schedule inside the exact frontier

For an admitted manifest, breadth-first search from all-old inside `F_M` returns a schedule with the minimum number of one-role mode advances.

**Proof.** Every rollout edge has unit cost. Breadth-first search discovers vertices in nondecreasing path length and stops at all-new. QED.

## Independent executable checks

Three structurally separate computations are retained:

1. the planner uses tuple configurations and reverse breadth-first reachability;
2. the checker uses integer base-three encodings and independently reconstructs closure, reverse reachability, path validity, and witness deletion-minimality;
3. the oracle uses forward depth-first reachability over integer states.

Agreement does not prove the specification itself correct, so the artifact additionally exhaustively enumerates all 256 assignments in a frozen two-service, eight-atom fragment and rejects four certificate-mutation classes for each of the 24 release-pair representatives.
