# Finite contract model and proof obligations

## Scope

The results in this note concern one finite rollout manifest. The manifest is trusted input: it declares a finite directed service graph, one old endpoint and one candidate new endpoint per service, local compatibility predicates, and mixed-version edge predicates. The algorithms do not inspect arbitrary program bodies or infer these predicates.

## Definitions

Let a manifest be `M = (S, E, P, Q)`, where `S` is an ordered finite set of service roles, `E` is a directed RPC edge set, `P` contains local Boolean obligations, and `Q` contains directional mixed-version obligations. A deployment configuration is a function `c : S -> {O, B, N}`:

- `O` exposes only the old endpoint;
- `B` exposes both endpoints through the declared bridge;
- `N` is the final abstract mode. In the runtime it denotes new preference, with old endpoints, session pins, and dual writes retained until harness teardown, not endpoint retirement.

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

Writing `n=|S|` and `m=|E|`, the tuple-based implementation costs `O(3^n (n^2+m))` mode/edge operations and `O(n 3^n)` stored mode words, excluding witness minimization. It retains at most `3^n` configurations, but each tuple contains `n` modes and constructing/hashing its `n` predecessors costs `O(n^2)` per vertex. A packed-state graph algorithm has different storage and arithmetic costs. The campaign graphs have at most five roles and 243 configurations.

## Theorem 2: admitted certificate soundness relative to the manifest

If the independent checker accepts an admitted certificate, the supplied path begins at all-old, ends at all-new, changes exactly one role by one mode at each step, and every path state belongs to the exact compatibility frontier.

**Proof.** The checker validates that every supplied state has exactly `|S|` integer digits in `{0,1,2}` before encoding it. On this domain base-three encoding is injective; without the domain check, `[4,-1]` would alias `[1,0]`. It independently reconstructs closure and reverse reachability, requires set equality, checks the Boolean admission bit against all-old membership, checks path endpoints, and checks every step difference. Frontier membership implies closure and target reachability by Theorem 1. No planner decision bit is trusted without reconstruction. QED.

This theorem is conditional on the truth of manifest predicates; it is not a proof of arbitrary endpoint implementations or adapter code.

## Theorem 3: blocking-witness minimality in the declared defect universe

Let `D` be all false atoms in the supplied manifest. The planner repairs all atoms, enumerates subsets of `D` by increasing cardinality, and returns the first subset `W` whose reapplication blocks all-old. Then `W` is minimum-cardinality among subsets of `D` that block the repaired manifest, and therefore deletion-minimal.

**Proof.** Every subset of size smaller than `|W|` is tested before `W` and found schedulable. Thus no smaller blocking subset exists. Deleting one atom yields a smaller subset and is therefore schedulable. QED.

The checker first requires a duplicate-free witness contained in the manifest's false-atom universe. It reconstructs the repaired manifest, reapplies `W`, checks blocking, then checks schedulability after every one-atom deletion. These checks establish deletion minimality, not a global cardinality minimum for arbitrary supplied witnesses. Minimum cardinality follows from the planner's increasing-size search; the compact checker additionally validates minimum cycle size. The claim is not a minimum source-code explanation or a shortest failing execution.

## Theorem 4: shortest schedule inside the exact frontier

For an admitted manifest, breadth-first search from all-old inside `F_M` returns a schedule with the minimum number of one-role mode advances.

**Proof.** Every rollout edge has unit cost. Breadth-first search discovers vertices in nondecreasing path length and stops at all-new. QED.

Every complete all-old-to-all-new path has exactly `2|S|` advances, since the sum of mode ranks increases by one each step from zero to `2|S|`. Thus the minimum-length statement is true but does not optimize an ordering. By the event-precedence normal form, every closed state of an admitted static manifest has a topological continuation: `F_M=C_M` in that case. Closed dead ends occur only in blocked manifests under these rules; see `compact-precedence-normal-form.md`.

## Independent executable checks

Three structurally separate computations are retained:

1. the planner uses tuple configurations and reverse breadth-first reachability;
2. the checker uses integer base-three encodings and independently reconstructs closure, reverse reachability, path validity, and witness deletion-minimality;
3. the oracle uses forward depth-first reachability over integer states.

Agreement does not prove the specification itself correct, so the artifact additionally exhaustively enumerates all 256 assignments in a frozen two-service, eight-atom fragment and rejects four certificate-payload mutation classes for each of the 24 release-pair representatives: admission flips, frontier changes, invalid schedules, and invalid witnesses. Frontier changes remove a state when nonempty or insert all-old when empty; schedules gain a multi-role step when admitted or a spurious path when blocked. Witness payloads add a spurious atom when admitted or an extra atom when blocked. In these 24 representatives all witness mutations fail the actually-false-atom check before deletion minimality is tested; the 96-mutation rejection count is not direct deletion-minimality coverage.
