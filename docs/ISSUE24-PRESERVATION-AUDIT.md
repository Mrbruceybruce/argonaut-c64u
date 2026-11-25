# Issue #24 — missing historical candidate provenance audit

## Publication status — 25 November 2026 UTC

This document's reconciliation was published in the six-document commit `5a635d8`;
Test Lab #237 passed **8/8 jobs for that exact commit**. See the fixed
[publication record](CURRENT-STATE.md#verified-publication-record--25-november-2026-utc)
for the full commit identity and CI link, and
[pending work and unchanged acceptance limits](CURRENT-STATE.md#pending-work-and-unchanged-acceptance-limits).
The original text below is retained as historical checkpoint evidence, including
its unpublished-candidate and then-current HEAD/preservation wording. Those status
claims do not apply to the later publication or establish complete preservation
of the missing `/tmp/argonaut-issue24-flash-20261122` checkout. File-level matches
remain limited evidence; acceptance exceptions and unresolved audit gaps persist.

Audit date: 25 November 2026 UTC. Documentation/evidence inspection only.
Primary and live `development`: `22bb4ba6c35f42db7fb2de38b96f609216fdd30c`.
No reconstruction, cleanup, reset, deletion, relocation, test execution or device
contact was performed. This document is an unpublished reconciliation candidate.

## Verified equivalence and its scope

The absent path `/tmp/argonaut-issue24-flash-20261122` was a detached independent
checkout at `489fae08c8a8e73d77047370e5fade55401a1541`, with origin pointing to the
primary local repository. It was not an auxiliary worktree registered in the
primary repository. Its historical closeout recorded ten pending source/test files.

All ten backups under
`/home/bruce/Documents/ChatGPT/Local Projects/work/argonaut-issue24-session-20261122-closeout/preserved-candidate-files`
match the SHA-256 values in that directory's `closeout.json`.
Eight match the published `86f84ca866b6a87574ccfb24d385996c9271bdde` blobs exactly:
five files in `c64u_browser` (`backup_dialog.py`, `core.py`, `file_service.py`,
`flash_dialog.py`, `settings_tab.py`) and three tests
(`test_configuration_dependencies.py`, `test_foreground_admission.py`,
`test_flash_session.py`). Two historical backups differ:

- `tests/ci_suites.json`: the historical FlashSessionTests count is 18; publication
  contains 20. The retained failed closeout explicitly records that mismatch.
- `tests/test_ultimate_menu_gate_a.py`: publication checks visible read-only native
  rows and no writes, and supplies `self.app.core` for the native preview fixture.
  The older backup uses expander-based checks and lacks that fixture assignment.

All ten corresponding files in the persistent bundle
`/home/bruce/Documents/ChatGPT/Local Projects/argonaut-qualification/issue24-native-flash/bundles/s1-r2-20261124/source`
match both the published correction and the current primary bytes. This is exact
file-level equivalence for those ten paths, not proof that the bundle is the old
checkout or that its full runtime, caches, untracked files or Git metadata survive.
The bundle's separate reconstruction report identifies source provenance at `4609c85`.

## Retained history and unresolved preservation

The persistent closeout above describes the earlier stopped/incomplete candidate.
Issue #24's [integration record](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24#issuecomment-7072755779)
and [publication record](https://github.com/Mrbruceybruce/argonaut-c64u/issues/24#issuecomment-7072996601)
record the later reviewed 15-file integration, local validation and publication.
Those reported historical outcomes do not substitute for missing original evidence.
Published Git blobs preserve the final tracked implementation.

The retained transcript at
`/home/bruce/Documents/Argonaut-Evidence/Issue24/NativeFlash/recovery/20261124/transcripts/rollout-2026-11-21T20-39-52-01a2011f-d219-71b3-8884-4895e8300b62.jsonl`
includes a directory-listing output at line 2066 (22 November 2026, 04:20:59 UTC)
that lists the candidate path. This proves only its reported presence at that
checkpoint. Later publication closeout found it absent. The disappearance time,
cause, final complete checkout inventory and any additional unpublished content
cannot be established from the inspected evidence. No missing files were recreated.

Persistent recovery/reconstruction reports distinguish exact recovered case payloads
from reconstructed support infrastructure. Original complete v7/S1–S4 run evidence
and original snapshot/seal/baseline manifests remain unavailable in those records;
later reviewed qualification is separate evidence, not restoration of the old runs.
Exact historical 19-cache exception equivalence remains unverified. Current ignored
files can be preserved without proving their historical equivalence. Persistent
local evidence is not a verified independent backup.

The four available auxiliary worktrees and seven primary artifacts are preserved.
The pre-existing `/tmp/argonaut-p44-registration` worktree registration points to
an absent path and remains unchanged; it was not pruned. No primary registration
exists for the historical Issue #24 independent checkout.

## Disposition and continuation

The missing candidate cannot be declared preserved or fully equivalent to a retained
replacement. Before future work depends on it, separately scope use of a verified
published baseline and retained evidence with these gaps explicit. This audit does
not authorize reconstruction or further execution. The R2 88-test slice did not run.
Publication, native/physical acceptance and issue closure remain separate gates.
Issue #24 remains Open / Backlog; all LED, Auto SID, C1, #49, #48 and RM-026/028/029
obligations remain unchanged. Full synchronization is not claimed.

Detailed per-path hashes, two historical-to-published diffs, source references,
preservation inventories and the cumulative review are retained under
`/home/bruce/.codex/.chatgpt-projects/g-p-6ab45977554c8191ac3a40c7db115846/closeout-reconciliation-20261125`.
Bruce / Argonaut maintainer retains evidence ownership.
