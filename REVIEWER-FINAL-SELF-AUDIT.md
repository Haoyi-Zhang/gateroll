# Reviewer-Oriented Final Self-Audit

This is an artifact self-audit, not an independent review or acceptance prediction.

## Contribution clarity
The paper now separates three layers: (1) a polynomial event-precedence characterization of the frozen manifest language; (2) independently checked compact certificates and minimum directional blockers; and (3) bounded user-space enforcement. The optional explicit frontier is no longer presented as the admission algorithm.

## Validity threats and resolutions

- **Algorithmic triviality / brute force:** resolved for the frozen model by the event-precedence theorem and implementation. Explicit enumeration remains an oracle and optional output-size-expensive view.
- **Shared-bug risk:** reduced through a separately coded checker, complete two-service enumeration, explicit-state cross-checks, mutation tests, and metamorphic properties. It is not eliminated in the sense of formal machine-checked proof.
- **Witness minimality:** strengthened from deletion minimality to cardinality minimum for the frozen language; the manuscript explicitly excludes minimum code repair and minimum failing trace.
- **Manifest truth:** reduced through finite typed-contract derivation and runtime preflight checks; executable-code/specification conformance remains trusted and visible.
- **Synthetic evaluation:** bounded by a tagged public-schema syntax probe and exact source hashes. The 24 release pairs remain controlled mutations and are not represented as historical incidents.
- **Toy-runtime external validity:** not hidden. The runtime demonstrates enforcement under local process, persistence, and fault controls; it does not support production-throughput or fleet-scale claims.
- **Baseline fairness:** comparison strategies remain information projections, not product implementations. Their purpose is to isolate omitted contract dimensions, not rank systems.
- **Scalability:** admission certificates are compact through 128-role controls. Full-frontier materialization can still be exponential in output size.
- **Reproducibility:** one command executes the original evidence plus compact and provenance audits. Measurement fields are excluded from semantic equality.
- **Literature integrity:** all bibliography keys are used and accompanied by metadata verification; reference quantity is not treated as novelty evidence.

## Irreducible limits
No self-audit can supply independent peer review, production deployment evidence, new human-subject evidence, or a proof that arbitrary adapters implement a finite specification. The paper's claims remain bounded accordingly.
