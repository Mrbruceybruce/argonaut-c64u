# Managed Library — foundation and explicit empty creation

## Phase 3B-2B.2 — read-only execution admission; pending independent review

Implementation baseline: `3137bd28fbd2b0392cf80e5880d96de8ba348a1c` (published
execution-journal foundation). This entry supersedes the older checkpoint status
below. This slice is uncommitted and pending independent review and publication.
There is no remote staging, FTP mutation, enabled Import/Stage action, recovery,
automatic resume, manifest change or game-content publication.

### Execution confirmation and guarded ownership

Core exposes internal `review_managed_execution`, `confirm_managed_execution` and
worker-only synchronous `admit_managed_execution`. Preparation is not execution
consent. The separate confirmation carries the redacted schema-3 transaction:
exact device/session, library UUID/root/path, manifest revision/digest, transaction
and plan digest, intended staging/final payload paths, sizes and SHA-256 values,
captured policy and a canonical SHA-256 of the ready snapshot evidence. Its message
states staging-only consequences and this checkpoint's read-only limitation.

The bounded volatile registry binds exact confirmation/authorization object identity,
Core instance, client identity, preparation generation and exact live snapshot owner
and evidence. Copies, serialized tokens, cross-Core capabilities and loaded journals
cannot grant authority. The 120-second monotonic deadline is inherited from the
existing snapshot-confirmation convention, starts at review and remains enforced
through admission. It is not extended on confirmation or progress. Registry sizes
remain at most 32 pending and 32 authorized entries; eviction loses authority.

Execution entry atomically removes the authorization before session, scheduler,
snapshot, capacity or FTP admission checks. Refusal, cancellation, expiration and
failure never restore it. Session/library invalidation clears pending capabilities;
Core generation and exact identities/preferences are checked repeatedly. Captured
schema/policy versions remain strictly validated. Execution authorization is never
serialized into schema-3 evidence.

Ready snapshots retain their original schema-2 transaction and a sealed file identity
(device/inode/size/mtime/ctime) captured after preparation synchronization. An exclusive
preparation-registry claim prevents discard or replacement and makes shutdown defer
cleanup. Validation opens each exact member through the retained directory descriptor
with no symlink following, rejects hard links, replacements, unexpected members/types,
permissions/owner changes and changed sizes, then independently hashes bounded
8192-byte reads. Actual reads, including canceled/failed reads, are charged separately
from preparation reads. The complete sealed set is checked again after hashing and
after the final remote checks. POSIX/cooperating-process assumptions remain; this is
not protection against arbitrary code running as the same OS user.

### Read-only admission sequence and resource lifetime

1. Consume confirmation; recheck live Core/client/session, library, policy, snapshot
   completeness and prior resource accounting; claim the exact snapshot owner.
2. Calculate the aggregate evidence reservation before acquiring a transport or
   creating a journal; reject insufficient operation, revision or byte capacity.
3. Reserve the existing device scheduler lane with busy rejection. Require the
   existing managed FTP adapter; create a fresh reserved schema-3 host writer in a
   caller-provided existing private journal directory. Record awaiting-confirmation,
   staging and snapshot-validation intent. These states do not prove remote writes.
4. Acquire a fail-fast adapter operation and its single managed FTP lease. Read the
   exact manifest and complete relevant library/games listings; reject ambiguous
   names, redirected paths, existing transaction directory or final destinations.
   Independently validate the owned snapshots, then repeat manifest/collision reads
   and recheck snapshot identities and the live cancellation/session/deadline gates.
5. Persist the snapshot-validation outcome with actual snapshot/control read counts.
   No remote mutation is dispatched. This read-only checkpoint durably ends the
   attempt as `canceled`, reason `read-only-admission-complete`, and returns
   `admission-checked` inspection evidence with `mutation_enabled=False`.
6. Release FTP first, drain the scheduler reservation, then release snapshot ownership.
   The returned report carries no lease, writer, authorization or future eligibility.

Only existing managed read/list operations are used (CWD/PWD/MLSD and SIZE/RETR/SIZE
plus existing session setup/closure). Admission disables LIST fallback and does not
reconnect/retry. Existing callers retain their previous listing behavior. Listing
wire data and manifest payload bytes share a 16 MiB control-read allowance; the
existing bounded parser rejects incomplete/malformed listings and unsuccessful data
reads are still charged. This counts received data-channel content, not FTP command
or reply framing. Snapshot validation has the exact planned payload allowance;
future control uploads retain a separate 1 MiB limit. No upload/readback allowance
is spent by this slice. Current disk ownership is measured against captured limits.

Absence observations are point-in-time evidence, not atomic FTP exclusion or a lock
against another remote writer. No future executor may treat this returned report as
permission: it must operate under a live fresh admission lifetime and separately
reviewed collision/mutation rules. This slice closes its attempt rather than creating
an active executor or a resumable journal. A repeated invocation is not an automatic
retry; the original journal UUID cannot be recreated in the same store.

### Evidence-capacity guarantee and limits

`import_capacity.py` enumerates the fixed operation plan: snapshot validation,
mkdir, transaction record, all uploads, then all readbacks. The sizing document uses
the actual transaction and paths and the current canonical encoder options (sorted
keys, compact separators, UTF-8, no ASCII escaping, terminating newline). For every
planned operation it includes the longest outcome/collision strings, a 64-character
hash, 19-digit size/accounting counters, and full UUID/sequence fields. It also includes
the longest state, 256-character bounded reason, maximum revision width, full
predecessor hash and maximum checkpoint width. Those simultaneous maxima need not
form a valid execution; their serialized length B bounds every valid planned prefix.

For K = 3 + 2N operations, reserve R = 2K + 6 revisions: two per operation, the five
normal state checkpoints (including initial prepared), and an extra terminal
uncertainty/failure checkpoint. Require K within the captured operation limit,
R <= 520, and B*R within the captured aggregate byte allowance (at most 1 MiB).
The live reserved writer checks each actual canonical encoding against B, charges
its actual length and revision only after durable persistence, and preserves B bytes
for every remaining reserved slot. Operation identities/paths must follow the exact
planned prefix; unrelated operations cannot spend its capacity. Existing schema-3
successor validation and store aggregate limits remain in force. The serialization
format and schema-1/2 behavior are unchanged; unreserved infrastructure writers remain
available for existing offline callers and are not execution authority.

This is a conservative logical journal-evidence allowance, not filesystem allocation,
free-space reservation, quota enforcement or a promise that fsync will succeed.
Large batches that meet payload limits can fail this stricter evidence bound; the
algorithm deliberately does not assume a 64-file batch fits. Actual canonical history
is usually smaller. No reservation is restored from disk, no old history is adopted,
and no journal capacity is automatically pruned. Missing trailing history remains
undetectable solely from the hash chain. Loaded schema-3 journals remain inspection-only.
A future mutator must require this live reservation and retain fail-closed persistence
handling; it cannot rely on an unreserved writer or this read-only result.

### Cancellation, uncertainty and remaining qualification

3B-2B.2F correction: the execution store now explicitly identifies a definite
pre-write refusal using an internal, non-serialized identity marker. Read-only
validation and collision checks precede the first persistence boundary. From before
the first directory fsync onward, failures are uncertain, including temporary-file
creation/partial writes, file fsync, replacement, directory fsync and cleanup. Unknown
or unclassified failures remain uncertain; exception class/message alone is never
proof of safety. The permanent advisory lock is coordination metadata, not checkpoint
or temporary evidence. Existing journal bytes remain unchanged on duplicate refusal.

Admission consumes authorization in both cases. A store-proven creation refusal
reports `not-created`, releases its snapshot pin and permits explicit discard or
normal shutdown cleanup, provided no independent blocker exists. Genuine uncertainty
still retains snapshots and blocks unsafe cleanup. A live writer's failed outcome
persistence remains blocked even if its particular append failed before writing.
No authority is restored, no retry/recovery is introduced, and no schema, reservation
formula or read-only terminal semantics changed.

Cancellation is checked before admission and between bounded reads and phase boundaries.
There is no consequential remote operation requiring deferred cancellation. Journal
persistence itself completes or fails before its live writer can advance. Failures
record truthful snapshot/control observations when the writer is usable; uncertain
persistence blocks that writer and preserves preceding intents. Failure after initial
checkpoint persistence also blocks snapshot cleanup. Snapshot identity uncertainty
retains ownership/evidence and blocks preparation/discard for later explicit review.
Shutdown invalidates admission, defers cleanup of executing snapshots and cleans only
after FTP/scheduler release when ownership and persistence remain certain. No automatic
recovery, remote cleanup, retry or journal-based reauthorization is introduced.

The 3B-2B.2F tests reproduce missing-parent and duplicate-journal refusals, checking
consumed authorization, unchanged artifacts, explicit discard and shutdown cleanup.
Real persistence syscall fault injection covers seven consequential boundaries while
retaining durable intents and blocking writers/cleanup. An unclassified
FileNotFoundError also stays uncertain. Cross-Core testing uses two actual Core
instances; shutdown tests directly observe FTP lease, scheduler reservation and
snapshot-pin release before cleanup, including the real managed localhost transport.
Final validation: 406 tests passed, zero failures, errors or skips.

New deterministic tests cover object identity/replay/expiry, admission failures,
Core/client/device/session/library/policy changes, manifest changes, complete listings,
collisions, independent hashing, modifications/replacements/hard links/symlinks,
concurrent discard/shutdown, cancellation at every observed check boundary, resource
exhaustion, logical capacity boundaries, maximum terminal evidence, journal failures,
lease contention/release and no remote mutations. Localhost tests exercise the real
managed adapter/lease/parser with fallback disabled. See CURRENT-STATE for final counts.

No physical C64U, GTK, cross-platform durability or power-loss acceptance is claimed.
Earlier C0/native-chooser/focus/lifecycle qualifications remain open. Independent
review must assess the conservative capacity proof, read-only terminal semantics and
ownership races. Remote-record encoding, live mutation handoff, external-writer
assumptions and physical C64U staging acceptance remain later separately authorized
work. 3B-3 recovery and 3C manifest publication remain separate. Stop here.


## Phase 3B-2B.1 — execution-journal foundation; uncommitted review checkpoint

Baseline: `6c35c5fb19c294ff8fa8a1c7438f0cf8a5bf9e52` (guarded host snapshots).
This slice is journal infrastructure only. It adds no Core execution admission,
active snapshot handoff, transport calls, remote writes, Import/Stage action,
recovery, remote cleanup, final placement or manifest publication. Schema-1/2 and
3B-2A behavior remain unchanged. The older pending-publication entries below are
historical; they do not describe this uncommitted checkpoint.

### Phase division for subsequent review

| Phase | Responsibility and completion boundary |
| --- | --- |
| 3B-2B | Core execution admission, remote staging, upload, independent readback, durable evidence and cancellation safety. Bounded physical C64U FTP staging acceptance is required before its Core FTP-write portion is complete. |
| 3B-2C | Supported workflow integration, staging progress/results, snapshot lifecycle and integrated physical qualification. Safety needed by an active executor cannot be deferred out of 2B. |
| 3B-3 | Explicit recovery inspection, reconciliation and disposition of interrupted or uncertain attempts; no automatic replay or adoption. |
| 3C | Separately authorized final placement and manifest publication. |

This records the proposed split; implementing 2B.1 does not authorize subsequent
slices. The exact execution authorization lifetime, physical target/matrix,
remote-record format and external-writer assumptions still require later review.

### Schema 3: immutable evidence, not authority

`import_execution.py` defines a separate execution schema. The explicit projection
factory accepts a schema-2 transaction, a SHA-256 reference to snapshot evidence,
and finite execution-specific limits. It never reads snapshots or establishes
ownership. The projection retains transaction UUID, plan evidence digest, exact
library/device/session binding, manifest revision/digest, policy version 2,
execution-policy version 1, intended staging/final paths, formats, sizes and hashes.
Host source paths, credentials and authorization tokens are excluded. Item hashes
bind the referenced snapshot evidence to the intended payload contract; this slice
does not itself inspect or authenticate that evidence.

The 3B-2B.1F correction validates every operation hash at direct construction and
again during journal validation: exact string type, with no coercion. Empty strings
are required for intents, not-started outcomes, collision refusals, snapshot-validation
and mkdir evidence; completed record/upload/readback evidence requires a canonical
64-character lowercase hexadecimal SHA-256. Other permitted partial/failure hashes
may be empty or canonical. Non-string values, including falsy values, are rejected
through construction, codec, writer and inspection paths without advancing state.

Canonical JSON, strict fields/types/UTF-8, duplicate-key rejection, bounded nesting,
64-file/256-operation ceilings and captured journal limits follow existing
conventions. Unknown versions, aliased/traversing paths, duplicate items/operation
UUIDs, gaps and mismatched operation identities are rejected. Schema-1/2 codecs,
pre-execution restrictions and reserved states retain their meaning. No automatic
conversion exists. Historical `.json` attempts with the same UUID cannot be
adopted by a new writer in the same store.

Schema-3 states:

`prepared -> awaiting-confirmation -> staging -> verifying -> verified-staged`

Pre-execution cancellation/failure is permitted. Active attempts may terminate as
canceled, failed or uncertain. An unresolved intent can terminate only as uncertain;
unknown outcomes require uncertainty. Rejected/not-started outcomes are terminal.
A completed operation can be recorded atomically with a terminal cancellation or
failure without pretending its consequence did not occur. All terminal states,
including verified-staged, prohibit resumption. Published is never supported.

The operation sequence is snapshot-validation, mkdir, transaction-record, all
uploads, then independent readbacks. Record completion requires upload and readback
accounting. Payload completion requires exact size/hash and corresponding byte
observations; every item must have completed readback before verified-staged.
Operation UUIDs and ordinal sequence identify intent/outcome pairs. Collision
observations distinguish absent/present/not-applicable; present can only accompany
a rejected, non-writing outcome. Caller-supplied absence is evidence, never a claim
of atomic FTP exclusion. No deletion, rename or manifest operation is representable.

### Accounting contract

Actual observations are separate from captured allowances. Counters are bounded
nonnegative integers (maximum `2^63-1`, excluding booleans) with checked addition:

- snapshot-validation bytes read (distinct from 2A source-read accounting);
- attempted upload bytes, confirmed sender-side bytes and uncertain send exposure;
- independent payload readback bytes;
- remote transaction-record/control upload and read bytes.

Attempted upload equals confirmed sender bytes plus uncertain send exposure.
Confirmed sender bytes do not prove durable remote storage. Operation byte counts
must agree with their associated observation counters. Intent has zero observations;
not-started may retain control reads but no payload writes. Collision refusal cannot
claim a write. Failure/uncertain records retain truthful over-budget observations;
active/success records must fit policy. Control uploads conservatively count bytes
offered for the remote record, not confirmed remote storage. Control reads include
record verification and bounded manifest/listing checks; record bytes are not game
payload. No actual I/O metering is activated by this slice.

Execution-specific limits are explicit: snapshot-validation allowance at most
8192 MiB and at least planned payload, control-upload allowance at most 1 MiB,
control-read allowance at most 16 MiB. These are bounded infrastructure contracts,
not approval of a future transfer policy or a guarantee that every batch fits.
Existing payload/upload/readback/disk policies remain unchanged.

### Durable local ownership and failure handling

`ExecutionJournalStore.create` returns a live, internal persistence writer only
for a fresh attempt. It is not connected to Core scheduling or execution APIs and
cannot dispatch anything. Writer methods record transitions, intent and outcome,
requiring the exact live previous checkpoint. Loaded/decoded objects are inspection
records, never live writers; the store exposes no resume API and rejects direct
save. These are ordinary application boundaries, not protection against arbitrary
code executing as the same OS user.

Each immutable checkpoint is retained as `<UUID>.execution-<six-digit-revision>`.
It contains its revision and the canonical SHA-256 of its predecessor. Loading
validates the entire contiguous chain and each expected-previous transition; gaps,
corruption and contradictory outcomes stop inspection rather than falling back.
The hash chain alone cannot detect deletion of an entire trailing suffix; an intact
earlier prefix remains inspection evidence, never proof that no later work occurred.
Separate names leave legacy `.json` journal behavior unchanged. The shared private
POSIX lock serializes cooperating writers. Files use exclusive 0600 temporary
creation, file flush/fsync, atomic host replacement into a new revision name, and
required directory fsync. Directory fsync is preflighted and unsupported/failing
synchronization is fatal for execution evidence, unlike legacy best-effort reporting.

The live writer advances only after persistence fully succeeds. Any persistence
exception blocks that writer, including failures after rename. The predecessor
file remains intact, so failed outcome persistence never removes the last durable
intent. The latest candidate may nevertheless be visible after a failed directory
sync: inspection does not certify its durability or authorize continuation. No
rollback, automatic retry, recovery deletion or remote-success inference occurs.
Temporary cleanup failures preserve the primary failure; uncertain leftovers require
later inspection. The hash chain is consistency evidence, not a cryptographic
ownership proof against a cooperating-user/host compromise.

Both each checkpoint and the aggregate retained encoded history are bounded by the
captured journal byte allowance (at most 1 MiB). There are at most 520 revisions
per attempt and 64 execution attempts per store, separately from legacy journals.
A history budget can exhaust before the file-count ceiling. This conservative
foundation stops before advancing, preserving the last intent if necessary; a
future executor must preflight sufficient evidence capacity before remote writes.
No outcome/failure capacity reservation is implemented yet. Reservation is mandatory
before execution admission or FTP writes, not an optional later optimization.
Filesystem allocation, temporary writes and crash leftovers are not OS disk quotas.
No automatic pruning or recovery is introduced.

### Validation and next checkpoint

The deterministic test command is:

```sh
PYTHONPATH=.:tests PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_import_execution tests.test_import_transaction tests.test_import_policy tests.test_import_snapshots tests.test_import_plan tests.test_managed_library
```

The reported run used the same unittest module list through a temporary runner
that rejects non-loopback socket addresses. New journal tests forbid sockets
entirely; existing planner/snapshot wire tests use localhost read-only fixtures.
Initial attempts found a missing `tests` import path, then sandbox socket denial;
those were environment setup errors, not skips or passing test evidence.

Final results are recorded in CURRENT-STATE. Existing tests were not rewritten.
Coverage includes schema-1/2 compatibility, malformed schema-3 records, transitions,
identity/order/collision rejection, partial-send accounting, mismatch and resource
bounds, write/replace/file-sync/directory-sync failures, immutable prior intents,
crash prefixes through verified-staged, private files and inspection-only reload.
No C64U, real FTP-write, GTK, cross-platform durability or power-loss acceptance was
performed. Existing C0/native-chooser/focus/lifecycle qualifications remain open.

Recommended next checkpoint, only after explicit authorization: review the new
schema/durability boundary and then define Core execution admission and guarded
snapshot ownership handoff. Remote-record encoding, transport metering and physical
FTP staging qualification remain later work. Stop here with changes uncommitted.

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

## Phase 3B-2A: versioned compatibility — approved; pending manual publication

The published schema-1 implementation at
`d2e37e3949690f935f4bf79388db9f33f47c15e0` remains supported. Its four
128 MiB planned payload ceilings, validation, state restrictions and inspection-only
loading keep their original meaning. `prepare_transaction` still constructs the
schema-1 contract. No stored record is automatically upgraded, resumed or adopted
as execution authorization.

`prepare_transaction_v2` is an explicit offline factory for future attempts.
It requires the same eligible original/revalidated plans and captured device,
session, library, revision and manifest digest. The frozen `ImportPolicy` captures:

- Batch payload ceiling: validated `import_batch_mib`, default 128 MiB,
  range 1–4096 MiB (Maximum Import Batch Size).
- Temporary host disk ceiling: validated `import_temp_mib`, default 512 MiB,
  range 1–8192 MiB (Maximum Temporary Disk Usage).
- Selected payload: each selected source's declared validated size, including
  selected duplicates, once; verification rereads do not add game payload.
- Planned upload and readback: new-item payload once per direction. Skipped
  duplicates do not consume planned transfer or spool capacity. Planned spool
  payload must fit the captured temporary-disk ceiling.
- Separate cumulative snapshot-read, upload and readback allowances. The factory
  captures twice the configured batch ceiling for each, bounded at 8192 MiB.
  These finite allowances reserve room for future verification work; they do not
  authorize retry or implement any I/O. Each allowance must cover planned payload.
- The existing 64-file, 1 MiB journal and 256-operation hard ceilings. The store
  remains limited to 64 journals.

Preferences use the existing host `app_options` model and atomic save path;
no preference-file schema change or Settings widgets are introduced. Missing
values receive bounded defaults. Non-integers (including booleans), zero,
negative and out-of-range values fail validation. Corrupt persisted values are
reported without rewriting the original file. Saving validates before replacement.
Changing preferences has no effect on an already captured transaction policy.

Schema-2 journals separately carry immutable `ResourceAccounting` observations:
snapshot bytes read, temporary-disk peak, upload bytes and readback bytes. They
start at zero; prepared/awaiting-confirmation records cannot claim I/O. Failed,
canceled or uncertain inspection evidence can retain an over-limit observation
rather than erase it. Counters are bounded nonnegative integers, not authority,
proof of successful verification, actual enforcement or available disk capacity.
No runtime accounting writer is introduced here.

Both journal versions retain exact field validation, strict UTF-8, bounded
strings/collections/nesting, incremental size-limited encoding, private POSIX
publication, exclusive temporary files, file fsync, atomic replacement, directory
fsync where supported, and stale-writer protection among cooperating processes.
Loading dispatches strictly on version and returns that version; mismatched fields,
unknown versions and attempts to replace an existing record with another schema
are rejected. Reserved execution/publication states and execution APIs remain
unavailable, including after round-trip or restart.

Phase 3A's 256 MiB planning-read budget is unchanged and includes verification
rereads and failed reads. Larger preferences may still be rejected during planning;
4096 MiB selection is not a promise of import eligibility. Existing per-format and
identity/eligibility limits also remain applicable.

Validation: 142 offline tests passed with no skips, including 14 new tests covering
schema-1 boundaries and round-trip, schema-2 policy/payload limits, preference
bounds and persistence failures, immutable capture, duplicates, journal round-trip,
corrupt/truncated data, exact encoding ceiling and one-byte-over rejection, UTF-8,
reserved authorization and no automatic version conversion. Existing 49 contract/
journal, 44 planner, 27 managed-library and eight preference tests remain passing.
No device contact or physical qualification. There are no source snapshots,
execution admission, FTP uploads, remote staging/readback, manifest publication,
enabled Import action, recovery cleanup or automatic retries. Phase 3B-2B and
later work are not implemented by this checkpoint.

### Schema-2 publication approval and documentation closure

Independent compact review approved this schema-2 compatibility checkpoint for
publication. It confirmed unchanged schema-1 limits and state restrictions,
byte-for-byte round trips for five existing schema-1 journal fixtures, immutable
schema-2 policy capture and separation of payload, temporary disk, planned
transfers and actual-I/O allowances. Reserved execution states remain unavailable.

Review evidence: 142 previously passing tests, plus 63 independently rerun focused
tests, all passing with no skips. Additional published-format compatibility and
eight schema-version/evidence rejection probes passed with network access forbidden.
No physical acceptance was required for this offline-only checkpoint.

Documentation closure prepares manual publication only. No actual transfer
metering, execution or remote staging exists; Phase 3A's 256 MiB planning-read
budget and POSIX/cooperating-writer journal limitations remain unchanged.
No later-phase work is complete, and no staging, commit or push was performed.

## Managed Import Phase 3B-2A — authorization and host snapshots approved; pending manual publication

Published compatibility baseline: `9b04bbe748a2216c32114116f3e2880c72d87cb5`
(`Add versioned managed import resource policies`). Earlier publication/status
entries below describe historical checkpoints.

Core now exposes internal review, explicit confirmation, one-use preparation and
owned-snapshot discard methods. No new UI action is exposed; Import remains
disabled. Confirmation states: “Stage and Verify prepares files but does not
import them into the Game Library.” In this slice all preparation is host-only;
there is no remote staging, upload, remote readback or manifest publication.

Consent lives only in bounded Core memory, binds the immutable schema-2 transaction,
device/session/library, manifest and policy, and expires after 120 seconds
(including preparation). A copied token, transaction UUID or journal is not consent.
Reconnect/selection changes invalidate pending consent. Preparation consumes it
once, even on admission failure, and uses the existing device scheduler lane with
busy rejection. Manifest identity/revision/digest are reread before and after
snapshots; state and captured policy are checked between streaming chunks.

Local sources are revalidated and read with fixed 8192-byte buffers; remote sources
use the existing session-bound managed FTP streaming reader. Exact size and SHA-256
must match the approved transaction. Source bytes consumed are charged even on
failure/cancellation, separately from payload and planned future transfers.
Private host snapshots enforce disk limits using allocated file blocks/logical
size and directory allocation, with space checks and bounded writes.

Snapshot ownership is descriptor-based, exclusive, restrictive and rejects symlinks.
Failure/cancellation cleans only proven owned files, releases FTP leases and returns
non-ready accounting evidence. Successful snapshots need explicit discard or Core
shutdown; restart never adopts/resumes or automatically cleans old directories.
Uncertain cleanup preserves unexpected content and blocks further preparation in
that Core session. Runtime evidence is volatile; durable transaction journals
remain separate and unchanged. No journal schema or reserved state is added.

Validation: 341 combined affected offline tests passed without skips, followed by
31 passing snapshot/admission tests including four additional lifecycle probes.
Fake FTP checks verified lease release and absence of mutation verbs. No physical
C64U contact or acceptance. Phase 3A's 256 MiB planning-read budget, schema-1/2
compatibility and POSIX/cooperating-writer journal limitations remain unchanged.
Remote staging, execution/publication, importing and Phases 3B-2B/3B-2C/3C remain
unimplemented by this checkpoint.

### Internal preparation contract and remaining limits

The internal Core methods are `review_managed_snapshots`,
`confirm_managed_snapshots(confirmed=True)`, `prepare_managed_snapshots`, and
`discard_managed_snapshots`. They are not wired to a desktop action. Confirmation
cancellation produces no capability. Registries retain at most 32 pending reviews
and 32 authorizations; object identity and Core ownership prevent reconstructing a
capability from serialized fields. The deadline is monotonic and does not renew.
One preparation or retained snapshot set may exist per Core instance; the device
lane still excludes other device work. Busy admission consumes consent, requiring
a new explicit review rather than retry. No independent dispatcher is introduced.

A caller supplies an existing private, user-owned POSIX host parent. Preparation
creates an unpredictable 0700 child and exclusive 0600 ordinal files. Path traversal
and symlinks in parent/source components are rejected. Cleanup checks device/inode,
regular-file type and link count using retained directory descriptors. It never
recursively deletes a directory tree or removes unexpected replacement files.
Cleanup completion is reported; unresolved cleanup blocks further attempts in the
current Core instance. Crash leftovers require explicit inspection outside this
slice; they are never adopted or automatically retried/removed after restart.

Disk accounting reserves only incremental growth beyond the current file footprint,
using the filesystem's reported allocation unit rather than a fixed block size.
Allocated blocks are measured in POSIX 512-byte units; logical host bytes written
are reported separately in runtime SnapshotEvidence, without a journal change.
Append-only writes credit already allocated capacity, so fragmented chunks do not
reserve the same block repeatedly. Partial writes and write exceptions retain
observed logical growth and peak disk evidence.

When st_blocks is absent, invalid or below logical size (for example delayed,
sparse or compressed allocation), rounded logical size is conservatively reserved
and evidence is labeled conservative-rounded rather than exact physical usage.
Directory footprint receives the same treatment. Allocation rounding uses f_frsize,
falling back to a positive f_bsize; if neither is usable, preparation stops.
Actual allocation is rechecked after writes and fsync: unexpectedly larger
allocation is recorded and stops preparation. Filesystem inode metadata, unrelated
process usage, delayed allocation and free-space races cannot be perfectly reserved;
ENOSPC and fsync errors stop preparation and preserve failure evidence. This is
application-side protection, not an operating-system disk quota.
Limits may reject a payload near the disk ceiling because filesystem overhead also
consumes space. The snapshot-read allowance counts actual source bytes at the read
boundary, including chunks whose sink later fails. Manifest control reads retain
the existing separate manifest bounds and are not counted as source payload.

Progress carries phase/current source, files completed/total and source bytes
read/total; verification progress precedes ready status. Job cancellation is checked
between chunks and at final admission. A cancellation arriving after successful
completion does not retroactively undo completion; owned snapshots can be discarded.
Snapshot results and failure accounting are non-resumable runtime evidence, not
remote execution capabilities. Existing durable journals are neither rewritten nor
advanced by preparation. No new persisted schema is necessary for this slice.

Shared FTP `read_into` accepts optional approved-size and cumulative-read limits;
existing callers without them retain their previous behavior. The existing reader,
lease manager and transport perform SIZE/RETR/SIZE and stream in 8192-byte chunks.
There is no FTP server-side copy assumption, upload, mount or launch operation.
A ready snapshot set alone cannot execute anything. Future execution must obtain
its own separately reviewed admission and recheck relevant state.

### Bounded cleanup/admission and disk-accounting correction — approved in final review

Cleanup now retains snapshot ownership/admission until its definitive outcome.
Concurrent preparation and repeated discard are refused while cleanup runs.
Failure or interruption retains a blocking uncertainty state and cleanup evidence;
shutdown neither races active cleanup nor retries uncertain content. No recovery
mechanism or deletion of unrelated files is introduced.

Disk reservation now charges only the increase beyond already-counted allocation.
Fragmented writes reuse existing capacity, including a one-byte append at the
1 MiB allocation boundary. Runtime evidence records host bytes written separately
from peak disk footprint. Actual allocation is checked after partial writes and
exceptions. Missing/insufficient allocation evidence uses a labeled conservative
rounded-logical-size fallback; an unavailable allocation unit stops preparation.

Validation: 170 targeted offline tests passed without skips, including 15 new
cleanup/admission and disk regressions, existing snapshots, managed FTP,
foreground/scheduler and schema-1/2 compatibility tests. No physical acceptance,
remote mutation or transfer execution is claimed. Authorization, session/library/
manifest guards, hashes, journals and Phase 3A planning remain unchanged.

### Initialization-cleanup exception correction — approved in final review

Constructor failures now record ownership and default to cleanup uncertainty before
attempting cleanup. If cleanup raises or is canceled, the original initialization
failure is re-raised with separate secondary failure evidence; cleanup is never
retried by the outer handler. Only a reported successful cleanup releases admission.
Failure before any owner can be recovered remains conservatively uncertain.

Runtime failure evidence retains the phase, primary/secondary exception types,
secondary OS error number when available, created directory path/identity, tracked
file identities and available byte/allocation accounting. Core retains an uncertain
owner and blocking state for later inspection. Ordinary retry, discard and shutdown
do not clear that state or retry uncertain cleanup. Unrelated content is preserved.
This adds no persisted journal schema or recovery mechanism.

Validation: 178 targeted offline tests passed with no skips, including eight new
initialization-cleanup cases and the exact allocation-setup failure followed by
interrupted directory removal. Authorization, guards, hashing, streaming,
disk-accounting rules and FTP services are unchanged by this narrow correction.

### Final independent review and publication readiness

Independent final review approved this authorization and host-snapshot checkpoint
for publication. The review confirmed Core-owned one-use authorization with a
120-second deadline and captured transaction/device/session/library/manifest/policy
identity; bounded 8192-byte local and remote streaming; exact size and SHA-256
verification; actual source-read and temporary-disk accounting; and incremental
filesystem allocation accounting. Cleanup retains admission until proven complete.
Initialization failures preserve primary and cleanup-error evidence; uncertain
cleanup blocks further preparation. Cancellation and managed FTP lease release
remain protected. No remote mutation or enabled Import action was introduced.

Evidence: 178 previously passing targeted offline tests; 23 independently rerun
focused tests all passed with no skips, including the eight initialization-cleanup
regressions and the original allocation-setup/interrupted-removal reproduction.
No physical acceptance is required for this offline checkpoint.

Limits remain: POSIX filesystem assumptions, allocation races and conservative
estimates rather than OS disk quotas, no implemented recovery for uncertain
cleanup, and non-resumable snapshots. No remote staging, upload, readback or
manifest publication exists. Phases 3B-2B/3B-2C/3C remain unimplemented.
