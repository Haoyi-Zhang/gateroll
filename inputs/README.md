# Input provenance and construction

`schema_families.json` is the exact consumed vocabulary input. It records normalized operation and field names from eight permissively licensed public interfaces, with source URLs and licenses. When an RPC service imports its payload schema from a second official file, both files are listed. No upstream implementation code is copied or executed.

`release_pairs.json` defines 24 controlled release pairs. Each pair assigns a public vocabulary to one of four local service topologies and describes an experimental change such as additive fields, response reshaping, session bridging, state recoding, authorization weakening, replay breakage, partial migration, or an ordering cycle. These are not historical upstream releases and must not be interpreted as defects in the referenced projects.

The generator includes each named pair, its fully repaired control, every singleton manifest atom, a deterministic tranche of directional combinations, and additional deterministic combinations of two to four atoms until each pair has 500 distinct cases.
