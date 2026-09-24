# Result surfaces

`raw/finite/` contains the generated 12,000-case corpus, one decision row per case, the certificate-mutation corpus, and the aggregate finite summary.

`raw/tiny_exhaustive.json` contains complete enumeration of the frozen two-service, eight-atom fragment.

`raw/campaigns/` contains one row per strategy run, one row per transaction, the certified controller journals, bounded execution events, and aggregate campaign and execution summaries. Disposable per-process state directories are not retained.

`summary/` is derived only from raw records by `scripts/aggregate_results.py`. The semantic summary excludes local timing. The timing summary is retained separately and must not be interpreted as a hardware-independent result.

`expected/semantic_summary.json` is the frozen semantic projection used by `scripts/verify_results.py`. It intentionally excludes planner latency, checker latency, campaign wall time, and per-request latency.
