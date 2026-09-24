# Checker structure and trust boundary

The certificate checker is separately implemented from the planner. It imports the shared manifest data classes and defect-application helper but does not import planner procedures. The two computations differ in representation and traversal:

| Obligation | Planner | Checker | Third oracle |
|---|---|---|---|
| State representation | mode tuples | base-three integers | base-three integers |
| Closure enumeration | product iterator | integer range | on-demand predicate |
| Viability | reverse BFS | independently coded reverse BFS | forward DFS |
| Schedule | forward BFS inside frontier | endpoint, step, and membership checks | decision only |
| Blocking witness | increasing-cardinality subset search | blocking plus every one-atom deletion | decision only |

Shared definitions are a deliberate specification trust boundary. Structural separation reduces accidental code-path reuse but does not constitute independent external verification. The exhaustive tiny fragment, 12,000-case agreement, and rejecting certificate mutations are executable checks against implementation mistakes; none proves that a false manifest reflects real code.
