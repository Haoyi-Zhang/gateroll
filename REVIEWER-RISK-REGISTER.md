# Reviewer Risk Register

This register distinguishes resolved implementation/specification risks from limits that cannot honestly be removed by packaging.

| Concern | Resolution or retained boundary | Evidence |
|---|---|---|
| Exponential planner appears to be a brute-force restatement | The frozen model is reduced to a `2|S|`-event precedence graph. Admission is linear in graph size; a minimum cycle witness is polynomial. Explicit frontier enumeration is retained only as a small-model oracle and optional operator view. | `compact_precedence/`, `proofs/compact-precedence-normal-form.md`, compact audit JSON |
| Planner and checker may share a bug | The checker has a separate graph construction and DFS cycle test. Decisions are also compared with explicit `3^n` reachability for all 16,384 two-service assignments and thousands of larger cases. | `scripts/run_compact_precedence_audit.py` |
| A blocked witness may be merely deletion-minimal | A false local atom is a size-one blocker; otherwise breadth-first shortest-cycle search yields a minimum-cardinality directional blocker for this frozen language. | proof note and mutation tests |
| Boolean manifests are trusted assertions | A finite typed-contract front end derives bounded facts and an independent validator replays its evidence. Residual code/specification conformance remains explicit. | `typed_contract/`, typed-contract results, supplement |
| Controlled pairs do not estimate production prevalence | The paper limits them to mechanism validation. Public interfaces provide vocabulary provenance; no frequency or field-deployment claim is made. | limitations and source inventory |
| Local JSON/TCP runtime may not predict production overhead | Runtime results are semantic and bounded. Timing is reported as local observation, not production performance or scalability. | raw transactions and resource logs |
| Baselines are straw products | They are labeled information projections, not named-product reimplementations. Their role is dimension ablation, not product ranking. | paper methodology |
| Availability can hide wrong answers | Availability and semantic violations remain separate axes and are derived from per-transaction records. | campaign CSV and reconciliation audit |
| Reference count may conceal weak or false citations | Every cited key is present, unique, used in text, and accompanied by machine-readable metadata verification. | reference audit |
| Artifact may be nondeterministic or irreproducible | Clean extraction, multiple hash seeds, two full runs, semantic-field comparison, PDF rebuild, and file hashes are recorded. | audit directory and final delivery verifier |

## Irreducible scope limits
The package is not a production deployment, a proof of arbitrary service code, a study of historical defect frequency, a network-partition protocol, or an independent peer review. These limits remain in the manuscript rather than being reframed as strengths.
