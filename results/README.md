# Result surfaces

`completion-oracle/` and `same-information/` are the current source-bound
scientific surfaces: exact inputs/replies, fresh full matrix/finite/test/control
records, same-contract null comparison and environment/source bindings. See
`../proofs/received-completions-and-policy.md` for scope and entry points.
`completion-oracle/full-tests.stderr` is the final 81-test log; `tests.stderr`
retains the earlier 77-test stage. `runtime-recount.json` verifies all current
matrix replies with the independent corrected completion map. Fresh derived
semantic/timing summaries and request latency CSV are in `completion-oracle/campaign/`.
`initial-stage-bindings.json` preserves the source snapshot before the recount
repair; the root bindings describe the current packet and final test stage.
Original failed audits, timings and historical raw/current records below are
unchanged. These results do not establish production validation or acceptance.

`current/` retains its October 6 Windows-local evidence. It retains
readable summaries, core CSVs, recount, the 46-pass/one-optional-metadata-skip
test log, five recovery control JSONs and the mechanism-disabled ablation.
`current/runtime-evidence.zip` contains the complete fresh raw records and logs,
all five recovery controls and the ablation with project-root-relative entries
under `artifact/results/current/`; unpack into a separate empty directory.
It contains no prior full campaign or historical failure directory. The main
matrix remains a regression, not the recovery test: dedicated controls restart
the proxy while intent is pending and obtain 12,12 after same-ID completion.
The mechanism-off ablation retains 12 then 11. Recovery is local, serialized,
single-proxy/controller and persistent-file conditional; lost-final-reply and
general concurrent histories remain unverified. See `current/README.md`.

The original fresh execution and control remain untouched in
`runtime_reproductions/`, alongside separate historical failures. The surfaces
below are retained historical data, not a substitute for the current run.

`raw/finite/` contains the generated 12,000-case corpus, one decision row per case, the certificate-mutation corpus, and the aggregate finite summary.

`raw/tiny_exhaustive.json` contains complete enumeration of the frozen two-service, eight-atom fragment.

`raw/campaigns/` contains one row per strategy run, one row per transaction, certified controller journals, execution events, and campaign/execution summaries. Per-process state directories are not present on this outer historical surface.

`summary/` is derived only from raw records by `scripts/aggregate_results.py`. The semantic summary excludes local timing. The timing summary is retained separately and must not be interpreted as a hardware-independent result.

`expected/semantic_summary.json` is the frozen semantic projection used by `scripts/verify_results.py`. It intentionally excludes planner latency, checker latency, campaign wall time, and per-request latency.
