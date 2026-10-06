# Current measured evidence

This is the completed 2026-10-06 Windows-local reproduction after the bounded
pending-intent recovery implementation, with five dedicated controls and a
mechanism-disabled ablation. It is copied measured evidence, not a new execution
or a fabricated replacement. Prior full results are not mixed into current.

## Sources and canonical layout

Source paths are relative to the artifact root:

- Main: `results/runtime_reproductions/dw-muw1wlby-full/` (3,656 files).
- Recovery controls: `results/runtime_reproductions/dw-muw1wlby-controls-v2/` (31 files).
- Mechanism-off ablation: `results/runtime_reproductions/dualwrite-muw1wlby-ablation/` (five files).

`runtime-evidence.zip` contains all **3,692 files** from those three sources,
with no prior full/cross-history inventory. Its project-root-relative entries
begin `artifact/results/current/`: main files retain their relative layout,
controls are mapped to `controls/`, and the mechanism-off control to `ablation/`.
The canonical path and archive entry names have no version/final suffix.
Original paths inside JSON/log records are unchanged. Unpack into a separate
empty directory for complete raw/state/receipt/intent/trace evidence.

Every archive entry was checked for byte equality against its original source.
The archive is **2,232,223 bytes**; expanded content is **22,772,386 bytes**.
Outer current has **37 files**: six top-level original status/verification/
recount JSONs, ten summaries, three finite CSV/JSONs, the tiny result, six core
campaign files, the test log, six recovery summary/control JSONs, ablation JSON,
archive, this README and `manifest.json`. Checks requiring complete raw files
must use the extracted tree, not only the compact outer CSV subset.

The previous 32-file current, including its original evidence ZIP, was moved
intact to the workspace outside the delivered project at
`D:/CodexProjects/2026-07-13/new-chat-4/repair_workspace/retained/P028/before-intent-integration/current/`.
The original source runs, earlier 12→11 control and all failed history remain
untouched. No runtime/test source was changed or executed by this integration.

## Full regression result

40 scenarios × six strategies produce 240 first-attempt jobs, 8,640 logical
transaction records and 8,649 workload proxy attempts, with zero job retry or
timeout. Certified has zero recorded violations, 16/16 expected preference
cutovers and 24 blocks; mean overall/affected/unaffected availability remains
98.1481%/95%/100%. All-N is preference with old endpoints/pins retained;
availability includes wrong successes, not correctness-filtered responses.

The finite result retains 12,000 agreements/checker accepts, 2,013 admits,
9,987 blocks and 96/96 mutation rejections. Tiny agreement is 256/256 (four
admits, 252 blocks). Semantic comparison matches the frozen expected file and
retained historical campaign with no discrepancies. Compact passes over 16,384
assignments, 12,000 seeded cases (6,000 explicit comparisons) and 27 scale controls.
Both the historic failed compact record and absent history inputs remain honest:
base `complete: true`; top-level `scientific_complete: true`,
`release_complete: false`, `complete: false`, history unavailable / `pass: null`.

The recorded suite runs 47 tests: **46 pass, one optional administrative
metadata-input skip**, no failures/errors. These are existing log results, not
new tests run by the documentation worker.

Main matrix time is **153.389480 seconds**, base sequence **195.644487 seconds**.
From the new timing JSON, available-authorized response medians range
**2.9423–3.2894 ms**, p95 values **23.9947–30.719935 ms**. These instrumented
Windows-local measurements include wrong successes and diagnostic overhead;
they are not portable speedups or production performance. Windows Job Objects
provide owned termination, not verified CPU/RSS caps.

## Actual bounded recovery and negative control

Certified B/N increments persist a per-target/key intent before either call.
While pending, reads and different-ID/effect writes on that key are refused;
role migration, preference advancement and old-route reset are also guarded.
Only same-ID/same-effect completion with two successful equal-value write
confirmations clears the intent. A committed half is not rolled back.

All five `controls/*/control.json` cases pass and retain their real traces:
secondary-down, primary-timeout, secondary-timeout, intent-only-crash-cut and
both-committed-crash-cut. Each restarts its owned proxy while pending and checks
intent persistence, both read barriers, new-ID/changed-effect rejection, three
controller guards, and unaffected `u0` availability. Same-ID completion permits
both routes and new preference to return **12,12**; completed-ID replay changes
neither state nor receipt set. The two crash-cut cases explicitly install
reachable persistent states before actual restart (`partial_response: null`),
not an observed instruction-boundary interruption. Secondary-timeout likewise
labels its staged primary-commit cut.

`ablation/counterexample.json` sets `pending_dual_write_enabled: false` and
retains the original unavailable dual write, physical 12/11 split and successful
reads **12 then 11**. It is the explicit negative control for the earlier missing
mechanism, not repaired-default behavior; the earlier control also remains saved.

The main 40×6 matrix itself still does not test interrupted-write recovery:
crashes occur between requests, duplicate/reorder resend one saved identifier,
and all four certified delay-tagged requests are denied guest increments before
endpoint execution. Certified has no service-timeout response or retry there.
Agreement at 324 certified B/N snapshots (244 after success) checks values and
receipt-ID sets only, not arbitrary intermediate states or receipt contents.

This local barrier requires one proxy/controller, serialized requests/actions,
initial agreement, truthful idempotent endpoints/migration, authentic labels,
stable unique IDs, no bypass writes and atomic same-machine intent/state/receipt
survival. The request lock does not synchronize competing authorities. Without
same-ID retry or endpoint recovery, a key can remain unavailable indefinitely.
Lost final replies after intent-clear still leave ambiguous client completion;
the received-completion oracle does not verify arbitrary such histories. No
exactly-once client acknowledgment, consensus/distributed commit, general
concurrent migration, persistent pin recovery, O-mode uncertain-write resolution,
controller journal replay or machine/storage-loss recovery is established.
The formal theorem premises remain unchanged; this is a scoped implementation
argument plus bounded tests, not a general runtime/concurrency proof.
