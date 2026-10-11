# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only managed import planning. A plan is evidence, never write authority."""
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import stat
from uuid import uuid4

from .api import BrowserError
from .game_library import GameLibraryService, GameSource
from .jobs import JobProgress
from .managed_library import LibraryError, LibraryIdentity, ManagedLibraryReader, relative_path
from .picker_model import PickerSelection, GAMES, safe_name
from .storage import storage_root

MAX_ITEMS = 64
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_RELEVANT_GAMES = 128
LIMITS = {'D64': 206114, 'CRT': 64 * 1024 * 1024}


class SourceBudgetError(LibraryError):
    code = 'import-source-budget'


class SourceBudget:
    """One operation's source-read allowance, including failed and repeated reads."""
    def __init__(self, limit=None):
        self.limit = MAX_SOURCE_BYTES if limit is None else limit
        self.consumed = 0

    @property
    def remaining(self):return self.limit - self.consumed

    def require(self, amount):
        if amount > self.remaining:
            raise SourceBudgetError(f'Source read budget exceeded: {self.consumed:,} of '
                f'{self.limit:,} bytes consumed. Required verification cannot finish; choose a smaller batch.')

    def consume(self, amount):
        self.require(amount)
        self.consumed += amount


@dataclass(frozen=True)
class ImportItem:
    source: PickerSelection
    format: str
    relative_destination: str
    size: int = 0
    sha256: str = ''
    local_identity: tuple = ()
    classification: str = 'invalid'
    message: str = ''


@dataclass(frozen=True)
class ContentEvidence:
    game_id: str
    path: str
    size: int
    sha256: str
    status: str


@dataclass(frozen=True)
class ImportPlan:
    id: str
    library: LibraryIdentity
    session_id: str
    revision: int
    manifest_sha256: str
    items: tuple[ImportItem, ...]
    content: tuple[ContentEvidence, ...]
    destination_entries: tuple
    bytes_read: int
    transfer_bytes: int
    completion: str = 'complete-review-only'
    source_bytes_read: int = 0

    @property
    def counts(self):
        return tuple((kind, sum(i.classification == kind for i in self.items)) for kind in
                     ('new', 'same-name-duplicate', 'content-duplicate', 'batch-duplicate',
                      'conflict', 'invalid', 'unverified'))

    def evidence(self):
        """Comparison for read-only revalidation; excludes new plan ID/work counters."""
        return (self.library, self.session_id, self.revision, self.manifest_sha256,
                self.items, self.content, self.destination_entries)


def validate_selections(selections, session):
    selections = tuple(selections)
    if not 0 < len(selections) <= MAX_ITEMS:
        raise LibraryError('Choose between 1 and 64 game files per review.')
    for item in selections:
        if (not isinstance(item, PickerSelection) or item.kind != 'file'
                or item.category != GAMES.category or not safe_name(item.filename)
                or Path(item.path).name != item.filename):
            raise LibraryError('Invalid typed game selection.')
        if item.scope == 'core-host':
            if not Path(item.path).is_absolute() or item.device_id or item.session_id or item.storage_root:
                raise LibraryError('Invalid local game selection.')
        elif item.scope == 'c64u':
            item.validate_session(session)
            if not storage_root(item.path) or storage_root(item.path) != item.storage_root:
                raise LibraryError('Managed import sources require USB or SD storage.')
        else:
            raise LibraryError('Unsupported source scope.')
    if len({(s.scope, s.storage_root) for s in selections}) != 1:
        raise LibraryError('Choose files from one source and storage root per review.')
    return selections


class ImportPlanner:
    """Injected listing/read-only byte access; no transport or credentials in results."""
    def __init__(self, listing, read, session, check, report):
        self.listing, self.read, self.session = listing, read, session
        self.check, self.report = check, report
        self.bytes_read = 0
        self.source_budget = SourceBudget()
        self.item_number = 0
        self.total = 0
        self.phase = 'validating-sources'

    def progress(self, path, amount):
        self.check()
        self.bytes_read += amount
        self.report(JobProgress(self.phase, self.item_number, self.total, 'files',
            'Reading ' + path, (('bytes_read', self.bytes_read), ('current_file', path))))

    def remote(self, path, limit, *, budget=None):
        previous = 0
        def progress(count):
            nonlocal previous
            self.progress(path, count - previous)
            previous = count
        self.check()
        data = (self.read(path, limit, progress, budget=budget) if budget is not None
                else self.read(path, limit, progress))
        self.check()
        if not isinstance(data, bytes) or not 0 < len(data) <= limit:
            raise LibraryError('Content is empty or exceeds its validation bound.')
        if previous < len(data):self.progress(path, len(data) - previous)
        return data

    def snapshot(self, identity):
        captured = []
        def read(path, limit):
            data = self.remote(path, limit)
            captured.append(data)
            return data
        reader = ManagedLibraryReader(self.listing, read, self.session, self.check)
        library = reader.load(identity.path, identity.library_id)
        if library.identity != identity:raise LibraryError('Library identity changed.')
        return library, hashlib.sha256(captured[0]).hexdigest()

    def entries(self, path):
        self.check()
        actual, entries = self.listing(path)
        self.check()
        if actual != path:raise LibraryError('Destination path changed.')
        return tuple(sorted((e.name, e.kind) for e in entries))

    def source(self, selection, format_):
        limit = LIMITS[format_]
        if selection.scope == 'c64u':
            return self.remote(selection.path, limit, budget=self.source_budget), ()
        path = Path(selection.path)
        if path.is_symlink():raise LibraryError('Choose a regular file, not a symbolic link.')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb', buffering=0) as stream:
            before = os.fstat(stream.fileno())
            self.source_budget.require(before.st_size)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
                raise LibraryError('Source is not a supported nonempty regular game file.')
            chunks = []; count = 0
            while True:
                self.check()
                remaining = self.source_budget.remaining
                if remaining == 0:
                    # Regular-file EOF can be checked without consuming another byte.
                    if os.fstat(stream.fileno()).st_size > count:self.source_budget.require(1)
                    break
                block = stream.read(min(1024 * 1024, limit + 1 - count, remaining))
                if not block:break
                self.source_budget.consume(len(block))
                count += len(block);chunks.append(block);self.progress(str(path), len(block))
                if count > limit:raise LibraryError('Source grew beyond its validation bound.')
            after = os.fstat(stream.fileno())
        def identity(s):return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if count != before.st_size or path.is_symlink() or identity(before) != identity(after) or identity(after) != identity(path.stat()):
            raise LibraryError('Source changed during planning.')
        return b''.join(chunks), identity(after)

    def prepare(self, selections, identity, expected_revision):
        selections = validate_selections(selections, self.session)
        self.total = len(selections)
        library, digest = self.snapshot(identity)
        if library.revision != expected_revision:raise LibraryError('Manifest revision changed. Reload the library.')
        entries = self.entries(identity.path + '/games')
        items = []
        for number, selection in enumerate(selections):
            self.item_number = number
            self.check()
            format_ = Path(selection.filename).suffix[1:].upper()
            destination = relative_path('games/' + selection.filename, 'games')
            item = ImportItem(selection, format_, destination)
            if format_ not in LIMITS:
                items.append(replace(item, message='Only D64 and CRT are supported.'));continue
            try:
                data, evidence = self.source(selection, format_)
                source = (GameSource.core_host(selection.path) if selection.scope == 'core-host'
                          else GameSource.c64u(selection.device_id, selection.path))
                inspected = GameLibraryService._inspection_from_data(source, format_, data)
                item = replace(item, size=len(data), sha256=inspected.sha256,
                               local_identity=evidence, classification='new', message='Source content verified by reading.')
            except (BrowserError, OSError) as exc:
                self.check()  # Cancellation/session errors must never become an invalid row.
                if getattr(exc, 'cancelled', False):raise
                if isinstance(exc, SourceBudgetError):raise
                item = replace(item, message=str(exc))
            items.append(item)

        # Only relevant catalog content is read; untouched entries remain explicitly unverified.
        self.phase = 'verifying-existing-content'
        evidence = []
        relevant_games = [g for g in library.games if any(i.sha256 and (
            i.relative_destination.casefold() == g.path.casefold() or
            (i.sha256, i.size) == (g.sha256, g.size)) for i in items)]
        if len(relevant_games) > MAX_RELEVANT_GAMES:
            raise LibraryError('Too many relevant catalog entries for one bounded review; choose a smaller batch.')
        if sum(g.size for g in relevant_games) > MAX_SOURCE_BYTES:
            raise LibraryError('Relevant catalog reads exceed the 256 MiB budget; choose a smaller batch.')
        for game in library.games:
            self.check()
            relevant = any(i.sha256 and (i.relative_destination.casefold() == game.path.casefold()
                            or (i.sha256, i.size) == (game.sha256, game.size)) for i in items)
            status = 'manifest-only'
            if relevant:
                try:
                    data = self.remote(identity.path + '/' + game.path, game.size)
                    status = ('verified' if (len(data), hashlib.sha256(data).hexdigest()) ==
                              (game.size, game.sha256) else 'mismatch')
                except (BrowserError, OSError) as exc:
                    self.check()
                    if getattr(exc, 'cancelled', False):raise
                    status = 'unavailable'
            evidence.append(ContentEvidence(game.id, game.path, game.size, game.sha256, status))

        for n, item in enumerate(items):
            if not item.sha256:continue
            named = [g for g in evidence if g.path.casefold() == item.relative_destination.casefold()]
            identical = [g for g in evidence if (g.size, g.sha256) == (item.size, item.sha256)]
            relevant = named + identical
            matching_entries = [(name, kind) for name, kind in entries
                                if name.casefold() == item.source.filename.casefold()]
            occupied = bool(matching_entries)
            kind = 'new'; message = item.message
            if any(g.status != 'verified' for g in relevant):
                kind = 'unverified';message = 'Relevant catalog content is missing, changed or unverified; blocked.'
            elif named and (len(matching_entries) != 1 or matching_entries[0][1] != 'file'):
                kind = 'unverified';message = 'Catalog path is missing, ambiguous or not a regular file; blocked.'
            elif named and any((g.size, g.sha256) != (item.size, item.sha256) for g in named):
                kind = 'conflict';message = 'Destination filename identifies different content; blocked.'
            elif occupied and not named:
                kind = 'conflict';message = 'Uncataloged destination already exists; no adoption or overwrite.'
            elif identical:
                kind = 'same-name-duplicate' if named else 'content-duplicate'
                message = 'Existing content verified by reading; skip duplicate.'
            peers = [p for p in items if p.sha256 and p.relative_destination.casefold() == item.relative_destination.casefold()]
            if len({(p.size, p.sha256) for p in peers}) > 1:
                kind = 'conflict';message = 'Batch contains different content for this filename; all conflicting rows blocked.'
            elif kind == 'new' and any((p.size, p.sha256) == (item.size, item.sha256)
                                      and p.classification in ('new', 'batch-duplicate') for p in items[:n]):
                kind = 'batch-duplicate';message = 'Same content selected earlier in this batch; skip.'
            items[n] = replace(item, classification=kind, message=message)

        # Repeat byte observations, not just timestamps, before returning a complete snapshot.
        self.phase = 'revalidating-sources'
        for number, item in enumerate(items):
            self.item_number = number
            if not item.sha256:continue
            data, local = self.source(item.source, item.format)
            if (len(data), hashlib.sha256(data).hexdigest(), local) != (item.size, item.sha256, item.local_identity):
                raise LibraryError('Source content changed during planning. Prepare a new plan.')
        self.phase = 'revalidating-existing-content'
        for game in evidence:
            if game.status != 'verified':continue
            data = self.remote(identity.path + '/' + game.path, game.size)
            if (len(data), hashlib.sha256(data).hexdigest()) != (game.size, game.sha256):
                raise LibraryError('Existing library content changed during planning.')
        self.phase = 'revalidating-destination'
        final, final_digest = self.snapshot(identity)
        if final != library or final_digest != digest or self.entries(identity.path + '/games') != entries:
            raise LibraryError('Destination evidence changed during planning. Prepare a new plan.')
        self.check()
        self.report(JobProgress('complete', len(items), len(items), 'files', 'Review prepared; importing is unavailable.',
                                (('bytes_read', self.bytes_read),)))
        return ImportPlan(str(uuid4()), identity, self.session.session_id, library.revision, digest,
                          tuple(items), tuple(evidence), entries, self.bytes_read,
                          sum(i.size for i in items if i.classification == 'new'),
                          source_bytes_read=self.source_budget.consumed)
