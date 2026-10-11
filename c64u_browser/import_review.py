# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK planning-only client; foreground jobs remain owned by Browser."""
from gi.repository import Gtk, GLib
from .picker_model import PickerMode, GAMES


CLASS_LABELS = {'new': 'New game', 'same-name-duplicate': 'Already present',
                'content-duplicate': 'Identical content', 'batch-duplicate': 'Repeated selection',
                'conflict': 'Filename conflict', 'invalid': 'Invalid game',
                'unverified': 'Existing content needs verification'}


class ImportReview:
    def __init__(self, view):
        self.view = view
        self.selections = (); self.plan = None; self.chooser = None
        self.context = None; self.generation = 0; self.closed = False
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add = Gtk.Button(label='Add Games…')
        self.add.connect('clicked', lambda *_: self.choose())
        self.prepare = Gtk.Button(label='Prepare Plan')
        self.prepare.connect('clicked', lambda *_: self.start())
        self.recheck = Gtk.Button(label='Revalidate Review')
        self.recheck.connect('clicked', lambda *_: self.start(revalidate=True))
        self.dismiss = Gtk.Button(label='Close Review')
        self.dismiss.connect('clicked', lambda *_: self.invalidate())
        self.execute = Gtk.Button(label='Import unavailable — planning only')
        self.execute.set_sensitive(False)  # Deliberately no execution signal handler.
        for button in (self.add, self.prepare, self.recheck, self.dismiss, self.execute):
            self.box.append(button)
        self.status = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.box.append(self.status)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=120)
        scroll.set_child(self.rows);self.box.append(scroll)
        self.busy_controls = (self.add, self.prepare, self.recheck, self.dismiss)
        self.invalidate()

    @property
    def app(self):return self.view.app

    def current(self):
        state = getattr(self.view, 'state', None)
        if state is None or state.status != 'valid' or not state.libraries:return None
        library = state.libraries[0];session = self.app.core.device_session()
        if (self.app.preferences.game_library_location != library.identity.preference()
                or state.session_id != session.session_id or library.identity.device_id != session.device_id):
            return None
        return library, session

    def update(self):
        self.add.set_visible(self.current() is not None)
        self.prepare.set_visible(bool(self.selections) and self.plan is None)
        self.recheck.set_visible(self.plan is not None)
        self.dismiss.set_visible(bool(self.selections))
        self.execute.set_visible(bool(self.selections))
        self.execute.set_sensitive(False)

    def invalidate(self):
        self.generation += 1;self.plan = None;self.selections = ();self.context = None
        if self.chooser:
            chooser = self.chooser;self.chooser = None;chooser.close_requested()
        while self.rows.get_first_child():self.rows.remove(self.rows.get_first_child())
        self.status.set_text('Planning and review only. No games will be imported.')
        self.update()

    def choose(self):
        if self.closed or self.app.busy or self.chooser or self.current() is None:return
        from .file_picker import FilePicker
        self.invalidate();context = self.current();generation = self.generation
        def selected(selections):
            self.chooser = None
            if self.closed or generation != self.generation or context != self.current():return
            if not selections:return
            self.selections = tuple(selections);self.context = context
            self.status.set_text(f'{len(selections)} files selected. Prepare Plan reads full source content and '
                'relevant existing games, then reads again to check for changes. Remote preparation can take '
                'several minutes. No uploads or catalog changes. Use the existing Cancel control while preparing.')
            for selection in selections:self.row(selection.path)
            self.update()
        self.chooser = FilePicker(self.app, selected, mode=PickerMode.OPEN_FILES,
                                  scopes=('core-host', 'c64u'), filter=GAMES, limit=64)

    def row(self, text):
        self.rows.append(Gtk.Label(label=text, xalign=0, wrap=True, selectable=True))

    def start(self, revalidate=False):
        if self.closed or self.app.busy or not self.selections:return
        if self.context != self.current():
            self.invalidate();self.status.set_text('Review is stale. Select sources again.');return
        previous = self.plan if revalidate else None
        if revalidate and previous is None:return
        self.generation += 1
        self.plan = None;self.update()
        while self.rows.get_first_child():self.rows.remove(self.rows.get_first_child())
        self.status.set_text('Preparing review — reading and validating content. Cancel is available in the operation controls.')
        generation = self.generation;library, session = self.context
        def valid():return not self.closed and generation == self.generation and self.context == self.current()
        def progress(snapshot):
            if valid() and snapshot.progress:
                p = snapshot.progress;details = dict(p.details)
                self.status.set_text(f'{p.phase}: {p.completed}/{p.total} files · '
                    f"{details.get('bytes_read', 0):,} bytes read\n{p.message}")
            return False
        def started(job):
            job.add_listener(lambda event: GLib.idle_add(progress, event.job) if event.kind == 'progress' else None)
        def done(snapshot):
            if not valid():return
            if snapshot.state != 'succeeded':
                self.status.set_text('Preparation canceled. No complete plan.' if snapshot.state == 'cancelled'
                    else 'Preparation failed. No complete plan. ' + snapshot.error.message)
                self.update();return
            self.plan = snapshot.result
            plan = self.plan
            self.status.set_text(f'Review complete — not execution authorization.\n{library.identity.path}\n'
                f'Device: {library.identity.device_id} · revision {plan.revision}\n'
                f'{len(plan.items)} selected · {plan.transfer_bytes:,} bytes would require transfer · '
                f'{plan.bytes_read:,} bytes read during preparation.\n'
                + ' · '.join(f'{CLASS_LABELS[kind]}: {count}' for kind, count in plan.counts) + '\n' +
                'This is a point-in-time snapshot. Revalidate after changes. Import is unavailable.')
            for item in plan.items:
                self.row(f'{item.source.path}\n{CLASS_LABELS[item.classification]}: {item.message}\n'
                         f'{item.size:,} bytes · {item.relative_destination}')
            if plan.content:
                self.row('Existing catalog evidence (manifest-only means stored claims, not verified bytes):\n' + '\n'.join(
                    f'{e.path}: {e.status}' for e in plan.content[:128]))
                if len(plan.content) > 128:
                    self.row(f'{len(plan.content)-128} additional catalog entries omitted from this bounded display; '
                             'no claim of complete catalog content verification.')
            self.update()
        def failed(exc):
            if valid():self.status.set_text('Preparation not started: ' + str(exc));self.update()
        self.app.run_file_job(lambda: self.app.core.prepare_managed_import(
            self.selections, library, session, previous=previous), done, started=started, failed=failed)

    def close(self):
        self.closed = True;self.invalidate()
