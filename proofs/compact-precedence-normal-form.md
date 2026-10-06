# Compact precedence normal form

## Statement
For the frozen Boolean rollout language, assume every service moves `O -> B -> N`, and the local and directional facts are static. Create events `B_s` and `N_s`, add `B_s -> N_s`, add `B_v -> B_u` when a non-self edge `u -> v` lacks new-to-old support, and add `N_u -> N_v` when it lacks old-to-new support. Self-edge directional guards are vacuous: one coordinate cannot simultaneously have the two different modes tested by either closure rule. A complete one-service-at-a-time rollout exists exactly when every eventually required local fact is true and this event graph is acyclic. Migration is required only for stateful services.

## Proof sketch
Any legal rollout orders all `2|S|` events. The intrinsic mode order and each failed directional atom force the corresponding precedence edge, so the rollout is a topological ordering. Conversely, a topological ordering never enters a configuration forbidden by a failed directional atom; the local premise makes every visited local mode valid. Executing the order therefore yields a closed rollout.

## Minimum blocking witness
A false local fact is a cardinality-one blocker. With all local facts true, a rollout is blocked exactly by a directed cycle. Because no precedence edge returns from an `N` event to a `B` event, every cycle lies wholly in a bridge-entry layer or wholly in a new-entry layer. A shortest directed cycle is therefore a minimum-cardinality set of directional defect atoms. Breadth-first search from each vertex finds it in polynomial time.

## Certificate soundness
An admitted compact certificate contains the manifest digest and a permutation of all events. The checker rebuilds the graph and verifies every precedence edge points forward. A blocked certificate contains either one false required local atom or a simple directed cycle whose edges map to false directional atoms. The checker independently computes the minimum blocker size (one if a local obligation is false, otherwise the shortest cycle distance) and compares both the atom count and the reported cardinality. A simple cycle alone proves blocking and deletion minimality, not a global cardinality minimum when another shorter cycle exists. These checks establish the claimed decision and minimum relative to the manifest. They do not establish that the manifest or adapters faithfully describe arbitrary executable code.

## Relationship to the explicit frontier
The explicit `3^|S|` frontier remains useful as an operator-facing set of alternate continuations and as a small-model oracle, but it is not needed to decide schedulability or produce a minimum blocker. The artifact retains explicit enumeration only for bounded cross-checks.

The separate `gateroll/` reference planner and campaign controller still use explicit certificates; the compact planner is an additional decision implementation, not a replacement already wired into the process runtime. The event graph has linear size. Abstract topological decision takes linear graph work; the shipped deterministic implementation also sorts vertices and adjacency lists, and canonical manifest hashing sorts edges. Those costs are not linear in the comparison model.

## No closed dead ends in an admitted static manifest

If all-old is admitted, every required local fact is true and the event graph is acyclic. Closure makes the completed events of any configuration predecessor-closed. Any such prefix can be extended by a topological order of the remaining events; local obligations cannot disable the extension. Hence `F_M = C_M` for an admitted manifest. Closed nonviable states do exist in blocked manifests: with one false bridge fact and no edges, `O` is closed but cannot advance, whereas `N` is closed and already at the target. The frozen model does not exhibit a safe greedy prefix that later gets stuck after starting an admitted rollout. All complete schedules also have exactly `2|S|` advances, so minimum step length does not distinguish their order.

## Compact frontier predicate
A closed configuration corresponds to a predecessor-closed set of completed events. Every nontrivial strongly connected component must be either wholly absent or wholly present, and one-event execution cannot enter an absent cyclic component. Local obligations are event guards: a disabled bridge event may be in the past for a service already in `N`, but no incomplete disabled event can be crossed. Thus a closed configuration is in the reverse-reachable frontier exactly when (1) the all-new target is closed, (2) every cyclic SCC is already completed, and (3) every incomplete event is enabled. The planner reports this summary; the checker reconstructs it with Kosaraju's algorithm, independently of the planner's Tarjan implementation.

## Traversal depth and implementation

The planner's Tarjan traversal keeps a DFS frame stack separately from its
unfinished-SCC vertex stack. A frame resumes its successor iterator after a
child completes, propagates the child's low-link value, and emits an SCC when
the low-link equals the discovery index. These are the recursive algorithm's
operations, with frames stored explicitly rather than on Python's call stack.
The checker retains the distinct Kosaraju algorithm: an explicit frame stack
records first-pass finishing order, then a stack traversal of the reversed graph
collects each SCC in reverse finishing order. Its separate three-color cycle
check is also iterative; a back edge to an active frame still rejects a cycle.
Each graph edge is visited a bounded number of times in these traversals,
excluding the existing canonical sorting, and auxiliary graph storage is linear.

`tests/test_compact_depth.py` exercises six structural manifests with 1,200
roles: bridge/new-layer DAGs, bridge/new-layer rings, a deep DAG with a disabled
bridge, and a deep ring with a smaller local blocker. It constructs expected
certificates directly from those shapes, checks them before calling the
planner, compares SCC summaries and minimum witness sizes, and checks all-old
and all-new frontier membership. This removes a reachable call-stack failure
in compact planning/checking without raising Python's recursion limit. These
are finite algorithm regressions, not 1,200-role process deployments or a
portable performance result; retained campaign and scale-audit runs are unchanged.
