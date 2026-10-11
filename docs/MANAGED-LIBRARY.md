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
