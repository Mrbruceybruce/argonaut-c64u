# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK confirmation for Core managed D64 jobs; no transport or launch implementation."""
from gi.repository import Gtk
from .api import BrowserError
from .managed_d64_execution import ManagedD64Outcome


class ManagedLaunchReview:
    def __init__(self, view):
        self.view=view;self.app=view.app
        self.generation=0;self.phase=None;self.plan=None;self.dialog=None;self.job=None
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.button=Gtk.Button(label='Review & Launch')
        self.button.connect('clicked',lambda *_:self.prepare())
        self.status=Gtk.Label(xalign=0,wrap=True,selectable=True)
        self.box.append(self.button);self.box.append(self.status)
        self.busy_controls=(self.button,)

    def current(self):
        row=self.view.rows.get_selected_row()
        state=getattr(self.view,'state',None)
        if self.view.closed or row is None or state is None or state.status!='valid':return None
        library=getattr(row,'library',None);game=getattr(row,'game',None)
        session=self.app.core.device_session()
        configured=self.app.preferences.game_library_location
        if (library is None or game is None or game.format!='D64'
                or not session.session_id or state.session_id!=session.session_id
                or library is not state.libraries[0] or game not in library.games
                or library.identity.device_id!=session.device_id
                or configured!=library.identity.preference()):return None
        return library,game.id,session,tuple(sorted(configured.items()))

    def update(self):
        self.button.set_sensitive(not self.app.busy and self.phase is None and self.current() is not None)

    def invalidate(self):
        self.generation+=1
        if self.phase=='preparing' and self.job is not None:self.job.request_cancel()
        self.job=None;self.phase=None
        if self.plan is not None:
            self.app.core.managed_d64_preflight.discard_plan(self.plan.plan_id)
            self.plan=None
        if self.dialog is not None:
            dialog=self.dialog;self.dialog=None;dialog.destroy()
        self.status.set_text('')
        self.update()

    def selection_changed(self):
        self.invalidate()

    def valid(self,generation,context):
        return not self.view.closed and generation==self.generation and context==self.current()

    def prepare(self):
        context=self.current()
        if self.app.busy or self.phase is not None or context is None:return
        self.generation+=1;generation=self.generation
        self.phase='preparing';self.update()
        self.status.set_text('Preparing launch review — validating the D64. Cancel is available in the operation controls.')
        service=self.app.core.managed_d64_preflight
        def factory():
            if not self.valid(generation,context):raise BrowserError('Game selection or connection changed.')
            library,game_id,session,_=context
            return service.prepare(service.selection(library,game_id,session))
        def started(job):
            if self.valid(generation,context):self.job=job
            else:job.request_cancel()
        def failed(exc):
            if not self.valid(generation,context):return
            self.phase=None;self.job=None
            self.status.set_text('Launch preparation failed. No launch command was sent. '+str(exc));self.update()
        def done(snapshot):
            plan=snapshot.result if snapshot.state=='succeeded' else None
            if not self.valid(generation,context):
                if plan is not None:service.discard_plan(plan.plan_id)
                return
            if self.phase!='preparing':return  # Duplicate delivery cannot replace the review.
            self.job=None
            if plan is None:
                message='Cancelled.' if snapshot.state=='cancelled' else getattr(snapshot.error,'message','Validation failed.')
                failed(BrowserError(message));return
            self.plan=plan;self.phase='review';self.show_review(generation,context,plan)
        admitted=self.app.run_file_job(factory,done,started=started,failed=failed)
        if admitted is False and self.phase=='preparing':failed(BrowserError('Another operation is in progress.'))

    def show_review(self,generation,context,plan):
        dialog=Gtk.Dialog(title='Review managed D64 launch',transient_for=self.app.window,modal=True)
        self.dialog=dialog
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        dialog.add_button('Launch',Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        text=(f'Game: {plan.title}\nDevice: {plan.device_id}\nLibrary: {plan.library_path}\n'
              f'Game path: {plan.game_path}\nFormat: {plan.format} · Verified size: {plan.verified_size:,} bytes\n'
              f'SHA-256: {plan.verified_sha256}\nMethod: DMA RUN_IMG\n\n'
              'Launching may interrupt or reset the running C64. Protocol acceptance does not prove playable state.')
        label=Gtk.Label(label=text,xalign=0,wrap=True,selectable=True,
            margin_top=16,margin_bottom=16,margin_start=16,margin_end=16)
        dialog.get_content_area().append(label)
        self.status.set_text('Review ready. Nothing has been launched. Explicit Launch confirmation is required.')
        def answered(widget,response):
            if self.dialog is not widget:return
            self.dialog=None;widget.destroy()
            self.plan=None
            if response!=Gtk.ResponseType.OK or not self.valid(generation,context):
                self.app.core.managed_d64_preflight.discard_plan(plan.plan_id)
                self.phase=None;self.status.set_text('Launch review dismissed. No command was sent.');self.update();return
            self.execute(generation,context,plan)
        dialog.connect('response',answered)
        def close_requested(widget):
            widget.response(Gtk.ResponseType.CANCEL);return True
        dialog.connect('close-request',close_requested)
        dialog.present();self.update()

    @staticmethod
    def outcome_text(result):
        if not isinstance(result,ManagedD64Outcome):
            return 'Launch outcome unavailable. Inspect the C64 before attempting another launch; no automatic retry will occur.'
        if result.outcome=='accepted':
            return 'Launch Accepted — DMA accepted the command. Playable state has not been verified.'
        if result.outcome=='rejected':
            return 'Launch Rejected — the launch command was not submitted. '+result.message
        return 'Launch Uncertain — the command may have been submitted. Inspect the C64 before attempting another launch. '+result.message

    def execute(self,generation,context,plan):
        self.phase='executing';self.update()
        self.status.set_text('Launching — revalidating content before DMA. Cancellation after submission cannot undo a launch.')
        delivered=[False]
        def present(result):
            if delivered[0]:return
            delivered[0]=True
            text=self.outcome_text(result)
            if self.valid(generation,context):
                self.phase=None;self.job=None;self.status.set_text(text);self.update()
            else:
                # Preserve consequential evidence without reviving stale rows/dialogs.
                status=getattr(self.app,'status',None)
                if status is not None:status.set_text('Previous launch on '+plan.device_id+': '+text)
        def factory():
            if not self.valid(generation,context):raise BrowserError('Game selection or connection changed before execution admission.')
            return self.app.core.execute_managed_d64(plan.plan_id)
        def failed(exc):
            self.app.core.managed_d64_preflight.discard_plan(plan.plan_id)
            present(getattr(exc,'result',None))
        def done(snapshot):present(getattr(snapshot,'result',None))
        admitted=self.app.run_file_job(factory,done,failed=failed)
        if admitted is False:
            self.app.core.managed_d64_preflight.discard_plan(plan.plan_id)
            if not delivered[0]:
                present(ManagedD64Outcome('rejected','foreground-admission',
                    'Foreground operation was not admitted.',plan.plan_id))
