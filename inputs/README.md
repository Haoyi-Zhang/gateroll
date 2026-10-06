# Input provenance and construction

`schema_families.json` records vocabulary inspirations from eight permissively licensed public interfaces, with normalized operation and field names, source URLs, and licenses. When an RPC service imports its payload schema from a second official file, both files are listed. The current generator and runtime do not load these operations or fields: the finite cases use a common Boolean contract model, and runtime requests use a common read/increment interface. No upstream implementation code is copied or executed.

`release_pairs.json` is the consumed input defining 24 controlled release pairs. Each pair assigns a family label inspired by a public interface to one of four local service topologies and describes an experimental change such as additive fields, response reshaping, session bridging, state recoding, authorization weakening, replay breakage, partial migration, or an ordering cycle. The labels do not select family-specific schema adapters. These are not historical upstream releases and must not be interpreted as defects in the referenced projects.

The generator includes each named pair, its fully repaired control, every singleton manifest atom, a deterministic tranche of directional combinations, and additional deterministic combinations of two to four atoms until each pair has 500 distinct cases.
