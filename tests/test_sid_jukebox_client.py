import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from c64u_browser.jobs import JobError
from c64u_browser.sid_format import SidChip
from c64u_browser.sid_jukebox import SidSource
from c64u_browser.sid_jukebox_client import (
    SidJukeboxClient, clock_text, error_text, mechanism_text,
    playback_preview_lines, sid_configuration_text, sid_models_text, source_text,
)


def metadata(**changes):
    values=dict(title='Tune',author='Author',released='1987',format='PSID',
        version=4,songs=3,start_song=2,playback_eligible=True,
        playback_classification='warning',mus=False,playsid_specific=False,
        chips=(SidChip(0xd400,'MOS6581'),SidChip(0xd420,'MOS8580'),
               SidChip(0xd500,'MOS6581-or-MOS8580')),clock='PAL-and-NTSC',
        sid_count=3,warnings=('Three SID warning',))
    values.update(changes);return SimpleNamespace(**values)


def tune(id_='tune', **changes):
    values=dict(id=id_,source=SidSource.core_host('/tmp/tune.sid'),
        metadata=metadata(),favorite=False,notes='',state='available',
        state_message='',title='Tune')
    values.update(changes);return SimpleNamespace(**values)


class SidJukeboxClientTests(unittest.TestCase):
    def setUp(self):
        self.catalog=Mock();self.playback=Mock()
        self.record=tune();self.catalog.get.return_value=self.record
        self.catalog.search.return_value=(self.record,)
        self.catalog.list_playlists.return_value=()
        self.playback.current_playback.return_value=SimpleNamespace(
            playlist_authorized=False,shuffle=False)
        self.client=SidJukeboxClient(self.catalog,self.playback)
        self.client.select('tune')

    def test_search_favorites_selection_and_metadata_presentation(self):
        self.client.query='author';self.client.favorites_only=True
        self.assertEqual((self.record,),self.client.records())
        self.catalog.search.assert_called_once_with('author',favorite=True)
        self.assertTrue(self.client.can_play_library(True))
        self.assertFalse(self.client.can_play_library(False))
        self.assertEqual('3SID · $D400 / $D420 / $D500',
                         sid_configuration_text(self.record.metadata))
        self.assertEqual('MOS6581 / MOS8580 / MOS6581-or-MOS8580',
                         sid_models_text(self.record.metadata))
        self.assertEqual('PAL or NTSC',clock_text('PAL-and-NTSC'))
        self.assertIn('This computer',source_text(self.record.source))

    def test_client_side_sorting_does_not_change_core_search_contract(self):
        alpha=tune('alpha',title='Alpha');alpha.metadata=metadata(author='Zulu',released='1988')
        beta=tune('beta',title='Beta');beta.metadata=metadata(author='Able',released='1987')
        self.catalog.search.return_value=(alpha,beta)
        self.client.sort_key='author'
        self.assertEqual(('beta','alpha'),tuple(item.id for item in self.client.records()))
        self.client.sort_key='released'
        self.assertEqual(('beta','alpha'),tuple(item.id for item in self.client.records()))

    def test_add_validate_metadata_remove_and_relink_forward_to_catalog(self):
        self.catalog.add.return_value='add-job'
        self.assertEqual('add-job',self.client.add_core_host('/tmp/a.sid'))
        self.assertEqual('core-host',self.catalog.add.call_args.args[0].scope)
        self.assertEqual('add-job',self.client.add_c64u('id:C64','/USB2/a.sid'))
        source=self.catalog.add.call_args.args[0]
        self.assertEqual(('c64u','id:C64','/USB2'),
                         (source.scope,source.device_id,source.volume))
        self.client.set_favorite(True);self.client.set_notes('notes')
        self.catalog.set_favorite.assert_called_once_with('tune',True)
        self.catalog.set_notes.assert_called_once_with('tune','notes')
        self.client.validate();self.catalog.validate_source.assert_called_once_with('tune')
        self.client.remove();self.catalog.remove.assert_called_once_with('tune')
        self.client.prepare_relink_c64u('id:C64','/SD/new.sid')
        self.assertEqual('c64u',self.catalog.prepare_relink.call_args.args[1].scope)
        self.client.execute_relink('plan',True)
        self.catalog.execute_relink.assert_called_once_with('plan',accept_changed=True)

    def test_blocked_and_unavailable_tunes_disable_play(self):
        self.record.metadata=metadata(playback_eligible=False,mus=True,
            warnings=('Compute! MUS data requires an external player.',))
        self.assertFalse(self.client.can_play_library(True))
        self.assertIn('MUS',self.client.library_blocked_reason())
        self.record.metadata=metadata(playback_eligible=False,playsid_specific=True,
            warnings=('PlaySID-specific data is incompatible.',))
        self.assertIn('PlaySID',self.client.library_blocked_reason())
        self.record.metadata=metadata();self.record.state='changed'
        self.record.state_message='Content changed.'
        self.assertFalse(self.client.can_play_library(True))
        self.assertEqual('Content changed.',self.client.library_blocked_reason())

    def test_playlist_crud_order_and_subtunes_forward_to_core(self):
        playlist=SimpleNamespace(id='playlist',title='List',items=())
        self.catalog.get_playlist.return_value=playlist
        self.client.playlist_id='playlist'
        self.client.create_playlist('New');self.catalog.create_playlist.assert_called_with('New')
        self.client.rename_playlist('Renamed')
        self.catalog.rename_playlist.assert_called_with('playlist','Renamed')
        self.catalog.add_playlist_item.return_value=SimpleNamespace(id='item')
        self.client.add_playlist_item(3)
        self.catalog.add_playlist_item.assert_called_with('playlist','tune',3)
        self.client.add_tune_to_playlist('other','second',2)
        self.catalog.add_playlist_item.assert_called_with('other','second',2)
        self.client.playlist_item_id='item';self.client.reorder_playlist_item(0)
        self.catalog.reorder_playlist_item.assert_called_with('playlist','item',0)
        self.client.remove_playlist_item()
        self.catalog.remove_playlist_item.assert_called_with('playlist','item')
        self.client.remove_playlist_items(('item','other'))
        self.catalog.remove_playlist_items.assert_called_with(
            'playlist',('item','other'))
        self.client.reorder_playlist_items(('other','item'))
        self.catalog.reorder_playlist_items.assert_called_with(
            'playlist',('other','item'))
        self.client.delete_playlist();self.catalog.delete_playlist.assert_called_with('playlist')

    def test_playlist_play_uses_playlist_item_independent_of_library_selection(self):
        item=SimpleNamespace(id='item',tune_id='tune',subtune=2)
        playlist=SimpleNamespace(id='playlist',title='List',items=(item,))
        self.catalog.get_playlist.return_value=playlist
        self.client.playlist_id='playlist';self.client.playlist_item_id='item'
        self.playback.prepare_play.return_value='preview-job'
        other=tune('other',title='Other library tune')
        self.client.select('other');self.catalog.get.side_effect=lambda id_:self.record if id_=='tune' else other
        self.assertTrue(self.client.can_play_playlist(True))
        self.assertEqual('preview-job',self.client.prepare_playlist_play())
        args=self.playback.prepare_play.call_args.args
        self.assertEqual(('tune',2,'playlist','item'),
                         (args[0],args[1],args[2].playlist_id,args[2].item_id))
        self.assertFalse(hasattr(self.client,'prepare_library_play'))
        self.client.execute_play('plan');self.playback.execute_play.assert_called_with('plan')
        self.client.discard_play('plan');self.playback.discard_plan.assert_called_with('plan')

    def test_playlist_play_defaults_to_first_item_and_now_playing_is_core_owned(self):
        first=SimpleNamespace(id='first',tune_id='tune',subtune=3)
        second=SimpleNamespace(id='second',tune_id='other',subtune=1)
        playlist=SimpleNamespace(id='playlist',title='List',items=(first,second))
        self.catalog.get_playlist.return_value=playlist
        self.client.playlist_id='playlist';self.client.playlist_item_id=None
        self.playback.prepare_play.return_value='job'
        self.assertEqual('job',self.client.prepare_playlist_play())
        self.assertEqual('first',self.client.playlist_item_id)
        self.assertEqual(('tune',3),self.playback.prepare_play.call_args.args[:2])
        snapshot=SimpleNamespace(tune_id='tune',selected_subtune=3)
        self.playback.current_playback.return_value=snapshot
        actual_snapshot,actual_tune=self.client.now_playing()
        self.assertIs(snapshot,actual_snapshot);self.assertIs(self.record,actual_tune)

    def test_previous_next_shuffle_and_boundary_results_stay_core_owned(self):
        self.playback.previous.return_value='previous-job'
        self.playback.next.return_value='next-job'
        self.playback.set_shuffle.return_value=SimpleNamespace(shuffle=True)
        self.assertEqual('previous-job',self.client.previous())
        self.assertEqual('next-job',self.client.next())
        self.assertTrue(self.client.set_shuffle(True).shuffle)
        self.playback.previous.assert_called_once_with();self.playback.next.assert_called_once_with()
        self.playback.set_shuffle.assert_called_once_with(True)
        boundary=SimpleNamespace(status='boundary',message='Already at the end.')
        self.assertEqual('boundary',boundary.status)

    def test_result_and_error_wording_preserves_outcomes(self):
        self.assertIn('outcome unknown',error_text(
            JobError('playback-outcome-unknown','private')).casefold())
        self.assertIn('reviewed Play',error_text(
            JobError('authorization','private')))
        self.assertEqual('safe',error_text(JobError('future','safe')))
        self.assertIn('local SID',mechanism_text('rest-attached-sid'))
        self.assertIn('play the validated content',
                      mechanism_text('rest-validated-c64u-sid'))

    def test_playback_review_exposes_takeover_unknown_duration_and_multisid(self):
        preview=SimpleNamespace(title='Three SID',source=self.record.source,
            selected_subtune=2,target_device_id='id:C64',
            mechanism='rest-attached-sid',sid_count=3,
            sid_addresses=(0xd400,0xd420,0xd500),
            sid_models=('MOS6581','MOS8580','MOS6581-or-MOS8580'),
            clock='PAL-and-NTSC',warnings=('Compatibility unverified.',))
        text='\n'.join(playback_preview_lines(preview))
        for expected in ('Three SID','Subtune: 2','id:C64','temporarily',
                         '3SID · $D400 / $D420 / $D500','PAL or NTSC',
                         'Duration: Unknown','Unsaved work','Compatibility unverified'):
            self.assertIn(expected,text)

    def test_gtk_client_has_no_transport_credentials_or_playback_rules(self):
        root=Path(__file__).resolve().parents[1]/'c64u_browser'
        text=(root/'sid_jukebox_tab.py').read_text()+(root/'sid_jukebox_client.py').read_text()
        for forbidden in ('UltimateClient','play_sid(', 'play_sid_data(',
                          '.password','_request_json','urllib','ftplib'):
            self.assertNotIn(forbidden,text)
        self.assertNotIn('Play now…',text)
        self.assertNotIn('prepare_library_play',text)
        gui=(root/'gui.py').read_text()
        self.assertNotIn('media_tab.select_file',gui)
        self.assertIn('Add to SID Jukebox',gui)


if __name__=='__main__':unittest.main()
