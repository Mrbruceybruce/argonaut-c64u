# Managed Library — foundation and explicit empty creation

Game Library now presents an explicitly managed C64U library, independently of
its preserved legacy reference catalog. The legacy catalog and Add/Relink picker
implementation remain intact for later reviewed adaptation. The Settings → Game Library
page provides explicit discovery, validated selection, empty creation and confirmed
host-only Forget. The main tab shows the selected read-only catalog or directs the
user to Settings. There is no import, scan, migration, artwork editing or launch.
Files game Add/Scan shortcuts are not offered by this view. Other Files actions,
SIDJuke and Drives are unchanged.

## Identity and discovery

The single `game_library_location` host preference is either null or an object
with `device_id`, `root`, `path` and `library_id`. A manually entered location has
an empty library ID until an explicit identity-bearing selection is saved.
The path must identify an `ARGONAUT_LIBRARY` folder inside USB/SD. An explicit
configured path may be nested; automatic discovery only checks the immediate
`ARGONAUT_LIBRARY` child of each advertised USB/SD root. Flash/Temp are excluded.

Configured location always takes priority. Missing/inaccessible, malformed or
identity-mismatched locations report unavailable with no fallback. Without a
configuration, complete root listings distinguish absence from inaccessible
storage. Discovery never recurses. Zero libraries reports not configured; one
is listed read-only; all candidates require explicit location selection, including
copied libraries sharing a UUID. Selection saves a host preference only. Nothing
is created, adopted, merged or transferred. Loading is an explicit foreground
operation with existing contextual cancellation and captured client/session checks.
Session or location changes invalidate both pending and displayed results.

## Manifest version 1

`manifest.json` is UTF-8 JSON, at most 4 MiB and 10,000 game entries. Duplicate
JSON keys and unknown fields are rejected. Required top-level fields:

- `schema_version`: integer 1 (not boolean).
- `library_id`: canonical nonzero UUID.
- `created_at`: ISO timestamp with timezone.
- `application`: `argonaut`.
- `revision`: nonnegative integer, at most 2^63−1.

`games` is an optional array, empty by default. Each entry requires a canonical
nonzero UUID `id`, a `games/` relative `path`, `format` D64 or CRT, positive
bounded `size`, and lowercase 64-character SHA-256 `sha256`. Optional `title`
defaults to the filename. Optional `metadata_path` and `artwork_path` must remain
under their corresponding subdirectories. Absolute paths, empty/dot/parent
segments, backslashes, colons and control characters are refused. Duplicate IDs
and case-insensitive content-path collisions are refused. The expected structure
is `manifest.json`, `games/`, `metadata/`, `artwork/`; an empty valid manifest does
not require those content directories to be populated or fetched.

Manifest loading checks the immediate required directory types, but does not
verify game bytes or playability. It does not enumerate game folders or fetch per-game metadata/artwork.
The manifest is authoritative for the displayed read-only summaries. Missing or
corrupt manifests are not valid empty libraries.

## Data and remaining work

C64U storage holds the managed manifest, game files and future portable metadata.
Host storage holds preferences; a future cache must be rebuildable. No SQL or
cache persistence is added in this phase. General Settings Undo/defaults preserve
the separately saved library location; Forget Library explicitly removes it after confirmation, without deleting files.

Further mutation/recovery workflows need separate review.
Explicit managed imports, content verification, legacy migration and managed
Relink remain later work. Recorded storage benchmarks rule out timestamp-only
content identity; this phase makes no incremental-indexing claim. No existing
catalog is rewritten or automatically migrated.

## Phase 2: empty creation

Create Library is available in Settings only in the unconfigured/no-library state. A remote
folder picker selects one exact USB/SD root, and Core returns a one-use captured
device/session/root/destination target. The separate confirmation names that
target. Cancelling either dialog performs no writes. An existing destination,
including a case-insensitive name collision, is always refused.

Execution uses the existing foreground scheduler and Core session-admission gate.
Reconnect is refused while creation owns that gate. A captured-session mismatch
stops subsequent writes and cleanup. The implementation never substitutes a root,
replays an uncertain mutation, or imports a game.

Creation uses the manifest as its completion record; it no longer writes a
hidden ownership marker. The three empty content directories and a staged
manifest are verified before publishing `manifest.json`. Final structure and
manifest bytes are read back after rename; atomic rename is not assumed.
Only then is the identity registered in host preferences. Revision is zero and
the game list is empty. Missing evidence, unexpected content, and invalid
structure/manifest failures have distinct messages.

Loading requires the immediate games, metadata and artwork directories and a
valid manifest. A staged manifest or a visible legacy creation marker reports
incomplete creation. Discovery locations and manifest schema are unchanged.
Omitted dot files do not affect new creation. A legacy hidden marker's absence
from a listing is not evidence of its removal; this correction does not clean up
or certify the failed physical-acceptance destination.

Failure reports the exact destination and phase. Automatic cleanup removes only
acknowledged empty directories before publication, using individual rmdir calls;
it never recursively deletes a folder or deletes residual files. Changed
sessions, uncertain replies or unexpected content leave recovery evidence.
Without the final manifest, partial creation cannot load as a valid library.
A lost rename reply may leave a complete verified library; recovery must inspect
that exact location, not retry or recreate it. A preferences-save failure also
preserves the verified remote library and reports failed registration.

The initial physical creation attempt found a valid empty manifest and the four
final entries, but MLSD omitted the old dot-prefixed marker expected by verification.
Offline regressions cover omitted dot entries, missing evidence, unexpected user
content, incomplete structure, and rename leaving both staged and final manifests.

Subsequent physical recognition acceptance with the corrected implementation
passed on C64 Founder's Edition, device identity `25BE71`, for the existing
`/SD/ARGONAUT_LIBRARY`. Manifest validation passed and the required `games/`,
`metadata/` and `artwork/` directories were recognized. The library UUID was
`2b8b17e2-6778-49f1-9fef-f8ee9bd5a691`, manifest revision `0`, with `0` games.
Repeated loading returned the same valid library identity. Normal shutdown
succeeded with exit code `0`.

This establishes successful existing-library recognition, not full qualification
of corrected fresh creation. At that checkpoint, corrected fresh creation had
not been physically retested. Absence of creation/duplicate prompts was not
separately confirmed during SD recognition.
No imports, scanning, cleanup or storage mutations were performed during
recognition acceptance; the existing library was left untouched.

Creation uses no metadata/artwork population, SQL, cache, migration or folder scan.


## Settings relocation and later acceptance evidence

The pending Settings relocation reuses the reader and creation service. Explicit
Discover Libraries lists candidates without changing the host association. Select
Library re-reads and validates the chosen identity under the captured session,
then saves before updating the selected view. Save failures preserve the prior
selection. Stale and busy actions refuse; Forget remains host-only and confirmed.

Bruce subsequently reported successful USB1 fresh-creation physical acceptance:
Founder `25BE71`, `/USB1/ARGONAUT_LIBRARY`, UUID
`56dc72d1-d607-4a7e-9174-d72f82155fb6`, revision 0, zero games. This is separate
from the SD recognition evidence above and supersedes its then-outstanding fresh
creation limitation. Settings relocation subsequently passed compact review and
the user-confirmed physical acceptance recorded below. The implementation and
acceptance documentation remain uncommitted and unpublished.

### User-confirmed Settings physical acceptance — passed

Bruce confirmed the following on GNOME Wayland using C64 Founder's Edition
`25BE71`. The two existing libraries remained distinct:

- SD: `/SD/ARGONAUT_LIBRARY`, UUID `2b8b17e2-6778-49f1-9fef-f8ee9bd5a691`.
- USB1: `/USB1/ARGONAUT_LIBRARY`, UUID `56dc72d1-d607-4a7e-9174-d72f82155fb6`.

Both were revision `0` with zero games. Settings → Game Library displayed
correctly and discovered both libraries. Explicit USB1 selection updated the
main Game Library without restarting; the selected library persisted after an
application restart. Explicit Discover Libraries populated the available choices.
Switching from USB1 to SD then updated the main Game Library to SD. Cancelling
the Forget Library confirmation preserved the selected host association.
Normal shutdown returned to the terminal with exit code `0`, as reported by Bruce.
No game imports or device-storage mutations were performed during this acceptance.

The existing warning `GtkText - did not receive a focus-out event` appeared;
it remains unresolved and is nonblocking for this acceptance. The separately
reproduced native GTK/PyGObject lifecycle crash also remains unresolved; no fix
is claimed. This acceptance does not certify screen-reader use, comprehensive
keyboard navigation, or new library creation. The earlier USB1 fresh-creation
acceptance and SD recognition evidence remain separate.

The reviewed Settings/Forget implementation and this acceptance record are ready
for manual publication preparation, but remain uncommitted and unpublished.
No Managed Import, Folder Scan, migration, Move Library, Delete Library or Phase 3
work is included.


## Phase 3A: read-only import planning — accepted; pending manual publication

The main tab offers Add Games → shared picker → Prepare Plan → Review. Selection
alone does not read game content or dispatch an import. Prepare Plan warns that
remote validation may take minutes. Local and C64U USB/SD D64/CRT sources retain
the complete typed picker context. Flash/Temp are excluded. The planner reuses
existing game-image validation without invoking legacy catalog mutations or
making firmware/playability guarantees.

Frozen ImportPlan/ImportItem/ContentEvidence records contain plan identity,
selected library identity, captured session and revision, exact manifest SHA-256,
source references, content hashes, sizes, local file identity, proposed games/
relative destinations, directory evidence, classifications, counts and read/transfer
byte totals. Plans contain no credentials or transport handles. No game IDs are
allocated or manifest entries changed in this planning-only slice.

Confirmed same-name/content and different-name/content duplicates are skipped;
batch duplicates use selection order. Same-name/different-content conflicts block
all affected batch rows. Uncataloged occupied destinations are not adopted.
Relevant manifest claims require byte verification; missing or mismatched content
blocks the affected candidate. Other catalog entries are explicitly manifest-only,
not proof of current content. Review displays at most 128 catalog evidence rows
and explicitly reports omissions. No filename conflict resolution is implemented.

Sources and verified relevant catalog content are read again before returning a
complete plan; the manifest and destination listing must still match. Revalidation
performs fresh reads and rejects changed evidence. Session, client or selected
location changes stop work and invalidate the UI review. External edits after
preparation cannot be detected without another read: the displayed review states
this limitation. Future execution admission must independently revalidate and
obtain explicit confirmation; no execution endpoint or enabled Import control
exists now.

Preparation is bounded to 64 selected files and 256 MiB of aggregate source bytes
read, including failed reads and verification rereads, plus
128 relevant catalog entries totaling at most 256 MiB. D64 remains bounded to
206114 bytes and CRT to 64 MiB. Hashing reads full content and repeated validation
increases work; no completion-time guarantee uses the Founder measurements.
The existing Core job and foreground owner report file counts, bytes read and
current path, with contextual cancellation. Canceled/failed preparation returns
no complete plan. The UI never runs validation on the GTK main thread.

Approved later design remains batch publication through one manifest revision,
small JSON metadata records, retained previous manifests/transaction evidence and
explicit read-only recovery. None of transfer, staging, metadata writes, manifest
publication, cleanup or recovery is implemented in 3A. Existing creation and schema
are unchanged. Phase 3B/3C/3D remain pending. Bounded physical acceptance
subsequently passed, with limitations recorded below.

Validation: 227 affected unit tests and 38 planning/managed-library/creation GTK
checks passed, with no skips. These include 31 new planner/Core/wire tests and
10 new UI/foreground checks. The managed-wire test inspects actual localhost fake
FTP commands, verifies no mutation verbs and unchanged remote bytes, and checks
lease release and absence of legacy catalog writes. The old foreground chooser
regression fails with FilePicker.emit on both current and published baseline;
its native-chooser assumption predates this slice. Dedicated B5 and shared-picker
checks passed. No physical device was contacted; existing GTK limitations remain.

Additional offline GTK checks passed: B5 (3), shared picker (16), game picker (9),
SID picker (4), Drives picker (3), C1 storage (6) and C4 layout (6): 47 checks,
or 85 with the 38 checks above. Broader foreground testing has one baseline
native-chooser error. Full C0 input testing reported six failures in 28 checks
on both current and baseline, with differing cases; two current keyboard failures
passed individually, while one also failed individually on baseline. C0 input
qualification remains incomplete; no new 3A-attributable failure was established.


### Source budget correction — re-review passed

The source allowance is exactly 268,435,456 bytes per preparation/revalidation
operation. It counts actual source bytes consumed, including failed or rejected
reads and every source verification pass. Counters never reset after a failed
candidate. Manifest/catalog reads use their separate existing bounds. Because
successful source validation requires rereading, a batch normally needs at least
twice its source-file sizes in this allowance; failed reads reduce what remains.

Local fstat and remote SIZE provide early admission hints, not content identity.
Local unbuffered reads and optional managed FTP receives cannot consume beyond
the remaining allowance. Remote bytes are charged before validation/buffering,
including bytes from a subsequently rejected length or final reply. At the exact
remote limit an EOF-only peek distinguishes completion from excess payload;
excess bytes are neither consumed nor buffered. Local regular-file size is
rechecked without another read at the limit. SHA-256 and existing content rules
are unchanged. Any budget exhaustion raises `import-source-budget` with consumed
and allowed counts, releases the normal read resources and produces no ready
plan. Required verification is never omitted to make a batch fit.

The correction adds an optional read-budget argument through the existing managed
read stack, not another transfer implementation or dispatcher. Existing consumers
without a budget retain their prior behavior. No creation, Settings, Forget,
picker, SIDJuke, Drives, legacy catalog or publication workflow was changed.

Validation: 286 tests passed in the combined planner/FTP/foreground run. The final
planner suite passed 44 tests after an additional end-to-end remote failure case;
13 budget regressions cover oversized and aggregate sources, failed/rejected
reads, underreported SIZE, repeated verification, exact limits, cancellation and
no partial plan. All 11 focused GTK checks passed, including budget-failure
invalidation. Localhost managed-wire checks verified zero remaining leases,
unchanged files and no mutation verbs. These correction checks were offline;
subsequent physical acceptance is recorded below. No later phase implementation
is claimed.

### Phase 3A GNOME Wayland physical acceptance — passed; pending manual publication

Read-only acceptance used source Development on C64 Founder's Edition `25BE71`,
with destination `/USB1/ARGONAUT_LIBRARY`, revision `0`. UI results were reported
by Bruce; process exit and repository authority were checked separately.

- Local planning classified one new game, proposing 1,050,688 transfer bytes.
  Explicit revalidation passed with unchanged classification and workload.
- Remote planning classified one new game, proposing 174,848 transfer bytes.
- Cancellation reported "operation canceled by request": no completed plan was
  returned, the UI returned to idle, and no automatic retry occurred.
- USB1 remained at revision `0`, with zero games. Import remained disabled;
  no game import or device-storage mutation occurred.
- Normal shutdown returned exit code `0`; no Argonaut runtime or launcher remained.

Limits: source filenames and SHA-256 values were not independently inspected;
the displayed library UUID and SD contents were not independently verified.
Session/library-change invalidation was not physically exercised. This is bounded,
user-reported UI acceptance, not broader physical qualification. The known
`GtkText - did not receive a focus-out event` warning appeared and remains
unresolved. No crash occurred in this run; the previously documented native
GTK/PyGObject lifecycle fault remains unresolved.

The source-budget re-review approved physical acceptance: 77 targeted tests
passed (44 planner, including 13 budget regressions, plus 33 shared-read/download
tests), as did 11 focused GTK checks and 10 additional exact-limit/one-byte-over
wire probes. No skips were reported; these are prior review results, not test
runs repeated during documentation closure. Phase 3B/3C/3D remain unimplemented.
Publication is prepared only; no staging, commit or push was performed in closure.

## Phase 3B-1: offline transaction contract — approved; pending manual publication

Implemented and approved by independent compact re-review against Phase 3A commit
`5996d7081411dfd1a17f55112ddad7679165c054`. Earlier publication-pending headings
are historical. This slice neither transfers game bytes nor creates remote paths.

`import_transaction.py` captures a new UUID, original and explicitly revalidated
plan UUIDs, a canonical evidence digest, library UUID/device/root/exact path,
session, manifest revision/digest, timestamp, resource budgets and frozen item
records containing source references/identities, sizes/hashes and staged/final
relative paths. Only verified new candidates become transfer items. Confirmed
duplicates are counted as skipped; duplicate-only batches and conflicts, invalid
content or unverified required evidence are rejected. Duplicate classification is
checked against catalog and batch evidence. Matching plans must have distinct
plan IDs and identical evidence. Construction performs no source or device reads.

Offline records cannot prove that supplied evidence is fresh or that a person
confirmed staging. The trusted future Core caller must provide the actual explicit
revalidation result, then require a separate confirmation and fresh session,
library, manifest, source and collision checks under existing B5 admission.
A transaction, UUID or loaded journal never grants execution or ownership authority.
No execution entry point, Stage and Verify control or enabled Import is added.

Future layout is a direct visible child of the library:
`argonaut-import-<canonical-transaction-uuid>/transaction.json`, with deterministic
`item-0001.crt` / `item-0002.d64` names. All stored staging paths are relative and
must exactly match generated names; final paths remain `games/<source filename>`.
Absolute/traversing/aliased staging paths and root escapes are rejected. A supplied
complete parent listing must not contain a case-insensitive transaction-name
collision; the future executor must freshly perform that check and never adopt
an existing directory. Dot-prefixed directories are excluded because of the
recorded C64U listing issue. This new layout has not been physically qualified.

### Separate proposed resource ceilings

| Resource | Offline ceiling |
| --- | ---: |
| Selected files, including skipped duplicates | 64 |
| Source snapshot bytes | 134,217,728 (128 MiB) |
| Temporary host spool bytes | 134,217,728 (128 MiB) |
| Upload bytes | 134,217,728 (128 MiB) |
| Remote readback bytes | 134,217,728 (128 MiB) |
| Host journal / future remote record | 1,048,576 (1 MiB) |
| Operation evidence records per journal | 256 |
| Recovery journals per private store | 64 |

Budgets are immutable and may be lowered, not raised beyond these ceilings. Each
transfer-item total must fit every independent byte ceiling. The 128 MiB proposal
matches the maximum source payload normally possible with Phase 3A's required
rereads; it does not redefine or share the 268,435,456-byte planning-read counter.
Later execution must charge actual consumption, including failed reads, and define
how additional verification passes fit independently reviewed budgets. Repeated
attempts must not evade limits. Spooling, disk-capacity checks and accounting are
not implemented here. These ceilings are proposals for execution review, not
performance guarantees or approval to transfer. Founder throughput is context only.

### Versioned journal and durability

`import_journal.py` defines strict schema version 1 JSON: transaction, state,
ordered operation evidence, last acknowledged checkpoint and bounded reason code.
The exact remote recovery location is derived from captured library path and UUID.
Unknown/missing/duplicate fields, oversized/truncated input, invalid types/paths,
unsupported states and inconsistent content observations are rejected. All nested
records are frozen; credentials, transport handles and arbitrary exception text
have no fields in the format. Source paths remain private host evidence.

The caller supplies an existing private user-owned directory. Host saves use a
0600 temporary file, flush and file fsync, atomic host replacement, then directory
fsync. A private advisory lock serializes cooperating writers, and an expected
previous journal prevents stale writers from overwriting newer evidence. New
journals must start prepared; each replacement must be one available pre-execution state transition.
Execution intent/outcome APIs are reserved and refuse calls in this slice. Existing journals cannot be adopted as new attempts.
Directory fsync unsupported by the filesystem returns False explicitly. Other
persistence errors propagate: an error after replacement means the new file may
exist, so stop and inspect rather than retrying remote work. Local temporary-file
removal never removes remote evidence. This host implementation uses POSIX
no-follow descriptors, ownership/permission checks and flock; other host platforms
are not qualified. No default journal directory or startup hook is installed.

The future remote `transaction.json` must be a separately reviewed, bounded,
verified projection of transaction identity, intended paths and hashes, excluding
host-only source details. Remote serialization/publication is not implemented.
Host atomic replacement does not imply FTP rename/overwrite atomicity.

### Offline state and recovery model

Prepared → awaiting confirmation is available, as are pre-execution canceled/failed
terminal transitions. Staging, verifying, verified-staged and published are
reserved: construction validation, transition APIs and journal loading reject them.
There is no serialized flag, UUID or callable confirmation mechanism that enables
execution. A later separately reviewed Core admission mechanism is required.
No manifest or catalog entry is changed. Terminal recovery records may retain
partial observations, but cannot claim a fully verified staged batch or resume.

Operations distinguish intent from completed, rejected and unknown outcomes.
Only inspection records for mkdir, transaction-record, upload and readback are modeled; deletion,
rename into games and manifest publication are excluded. Persisted records reject operations after an unresolved/rejected observation,
readback before all uploads, uploads after readback, and a checkpoint differing
from the acknowledged prefix. No terminal state can resume.
Upload/readback observations retain partial counts and hashes on rejected/unknown
outcomes without claiming verification. Cancellation during an outstanding command
retains its intent; restart loading marks such evidence as requiring inspection,
not success or automatic retry. Partial multi-file evidence survives failure.
Disconnect, session replacement and hash mismatch use bounded reason codes.

The journal itself is untrusted recovery evidence, not cryptographic ownership
proof. Recovery loading performs only bounded host reads and returns immutable
evidence; it never reconnects, cleans up, rebinds a session or resumes a transfer.
A fresh explicit inspection must resolve uncertain paths. No automatic remote
cleanup, recursive deletion, existing-game overwrite or manifest update exists.

### Validation and next checkpoint

35 deterministic new tests cover identities, matching revalidation, immutability,
eligibility/duplicates, safe paths and pre-existing-path refusal, independent
budget boundaries, valid/invalid transitions, partial/canceled/uncertain evidence,
strict serialization, corrupt journals, restart identity, file/dir fsync behavior,
expected-previous replacement, private permissions/symlinks, and journal quotas.
The affected offline run passed 106 tests (35 new, 44 planner and 27 managed-library),
with no skips. Existing implementation/tests remain unchanged; no GUI or shared
transport code changed, so unrelated GTK suites were not rerun.

Next checkpoint: manual publication of the approved Phase 3B-1 foundation. 3B-2 transfer/readback, 3B-3 recovery integration and
Phase 3C publication remain pending. No physical transfer/import acceptance claimed.

### Phase 3B-1 safety correction — re-review approved

The earlier 106-test/35-new-test result above is historical. Correction validation
passed 120 affected offline tests: 49 contract/journal (including 14 added safety
regressions), 44 planner and 27 managed-library tests, with no skips.

Root causes and corrections:

- The original offline model exposed execution-state transitions without an
  authorization boundary. Execution states and intent/outcome mutation APIs now
  refuse ordinary callers; prepared/awaiting-confirmation and terminal inspection
  evidence remain available. Persisted authorization/confirmation fields are unknown
  fields and rejected. No execution admission mechanism is invented in 3B-1.
- Persisted phase/checkpoint consistency was incomplete. Reserved phases are now
  rejected outright. Recovery evidence must have contiguous integer sequences,
  valid path ownership relationships, acknowledged directory/record prerequisites,
  all uploads before readback, no upload after readback and no operations after
  unresolved evidence. The checkpoint must equal the completed prefix. An intent
  cannot claim consumed bytes or a hash. Unknown outcomes require uncertain state;
  canceled/failed records cannot claim full-batch staged verification. Invalid
  evidence is rejected rather than repaired. Genuine partial results remain intact.
- Encoding previously assembled a full JSON string before enforcing its cap, and
  timestamp length was unbounded. Validation now bounds text (4096 characters
  generally, 64 for timestamps, 256 for session/device IDs, 255 for filenames and
  256 for reason codes), integers (128-bit structural ceiling plus field bounds),
  nesting (12 levels), tree nodes (200,000) and collections (field-specific item/
  evidence limits, with a 10,000-element structural ceiling for plan evidence).
  Invalid Unicode surrogates are rejected. Incremental strict UTF-8 encoding keeps
  its output buffer within the captured journal limit, reserving the final newline;
  no full JSON string is built. Input remains capped at 1 MiB and nesting is checked
  before JSON parsing. Exact-limit, excessive-field, collection, depth, UTF-8 and
  one-byte-short encoding regressions pass.

Budget terminology: this slice validates planned payload ceilings only. It does
not meter snapshots, spool I/O, uploads or readback; actual consumption accounting
belongs to 3B-2. A truthful rejected/unknown observation may exceed a planned byte
limit and must not be discarded to make the record fit that plan. Observation
counts are bounded nonnegative 63-bit integers for serialization, not I/O limits;
such evidence grants no authorization or retry permission. Phase 3A's planning
allowance is unchanged.

Future execution evidence must distinguish intended (not dispatched), submitted/
started, acknowledged, independently verified, failed and uncertain. The current
inspection format's completed upload denotes an acknowledged size/hash observation;
a separate completed readback denotes verification of that file, not publication.
The current format does not introduce a started dispatcher state. A submitted
operation without authoritative completion must later be recorded as unknown/
uncertain, not completed or safely unsubmitted. Those future protocol details,
Core admission and consumption metering require separate 3B-2 review.

Durable host replacement, expected-previous protection, restrictive permissions
and POSIX limitations remain. Loaded recovery evidence is inspection-only and
cannot be saved as execution progress. No physical device contact, remote staging,
transfer execution, recovery automation, manifest changes or UI changes occurred.

### Phase 3B-1 publication approval and documentation closure

Independent compact re-review approved Phase 3B-1 for publication. Reviewed
capabilities include immutable transaction/recovery contracts, strict plan
eligibility and safe staging paths, reserved execution/publication states and
rejection of forged authorization fields, consistent operation ordering and
acknowledged checkpoints, bounded encoding/validation, durable POSIX host-journal
publication and inspection-only restart recovery.

Evidence: 120 previously passing tests, no skips (49 contract/journal, 44 planner,
27 managed-library). The final review additionally passed the 1 MiB journal-load
boundary, one-byte overflow, quoted structural-character and multibyte UTF-8
encoding boundary probes. These are prior results; tests were not rerun during
documentation closure. No physical acceptance is required for this offline-only
checkpoint.

Limitations remain: POSIX host filesystem guarantees and cooperating-process
locking only; planned payload ceilings are not actual-I/O metering. There is no
execution admission, FTP upload, remote staging, automatic retry, recovery cleanup,
manifest publication or enabled Import action. Phases 3B-2, 3B-3 and 3C remain
pending. Documentation closure prepares manual publication only; no Git staging,
commit or push was performed in this pass.
