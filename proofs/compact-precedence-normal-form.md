# Compact precedence normal form

## Statement
For the frozen Boolean rollout language, assume every service moves `O -> B -> N`, and the local and directional facts are static. Create events `B_s` and `N_s`, add `B_s -> N_s`, add `B_v -> B_u` when edge `u -> v` lacks new-to-old support, and add `N_u -> N_v` when it lacks old-to-new support. A complete one-service-at-a-time rollout exists exactly when every eventually required local fact is true and this event graph is acyclic.

## Proof sketch
Any legal rollout orders all `2|S|` events. The intrinsic mode order and each failed directional atom force the corresponding precedence edge, so the rollout is a topological ordering. Conversely, a topological ordering never enters a configuration forbidden by a failed directional atom; the local premise makes every visited local mode valid. Executing the order therefore yields a closed rollout.

## Minimum blocking witness
A false local fact is a cardinality-one blocker. With all local facts true, a rollout is blocked exactly by a directed cycle. Because no precedence edge returns from an `N` event to a `B` event, every cycle lies wholly in a bridge-entry layer or wholly in a new-entry layer. A shortest directed cycle is therefore a minimum-cardinality set of directional defect atoms. Breadth-first search from each vertex finds it in polynomial time.

## Certificate soundness
An admitted compact certificate contains the manifest digest and a permutation of all events. The checker rebuilds the graph and verifies every precedence edge points forward. A blocked certificate contains either one false local atom or a simple directed cycle whose edges map to false directional atoms. These checks establish the claimed decision relative to the manifest. They do not establish that the manifest or adapters faithfully describe arbitrary executable code.

## Relationship to the explicit frontier
The explicit `3^|S|` frontier remains useful as an operator-facing set of alternate continuations and as a small-model oracle, but it is not needed to decide schedulability or produce a minimum blocker. The artifact retains explicit enumeration only for bounded cross-checks.

## Compact frontier predicate
A closed configuration corresponds to a predecessor-closed set of completed events. Every nontrivial strongly connected component must be either wholly absent or wholly present, and one-event execution cannot enter an absent cyclic component. Local obligations are event guards: a disabled bridge event may be in the past for a service already in `N`, but no incomplete disabled event can be crossed. Thus a closed configuration is in the reverse-reachable frontier exactly when (1) the all-new target is closed, (2) every cyclic SCC is already completed, and (3) every incomplete event is enabled. The planner reports this summary; the checker reconstructs it with Kosaraju's algorithm, independently of the planner's Tarjan implementation.
