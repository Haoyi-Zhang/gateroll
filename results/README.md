# Result surfaces

`current/` is the single fresh Windows-local evidence surface. It retains
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

`raw/campaigns/` contains one row per strategy run, one row per transaction, the certified controller journals, bounded execution events, and aggregate campaign and execution summaries. Disposable per-process state directories are not retained.

`summary/` is derived only from raw records by `scripts/aggregate_results.py`. The semantic summary excludes local timing. The timing summary is retained separately and must not be interpreted as a hardware-independent result.

`expected/semantic_summary.json` is the frozen semantic projection used by `scripts/verify_results.py`. It intentionally excludes planner latency, checker latency, campaign wall time, and per-request latency.
