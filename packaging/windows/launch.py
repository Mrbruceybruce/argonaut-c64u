# SPDX-License-Identifier: GPL-3.0-or-later
import os,sys,tempfile,json
from pathlib import Path
import c64u_browser
metadata_path=Path(c64u_browser.__file__).parent/'_build.json'
package_metadata=json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
if package_metadata.get('development') is True:
 os.environ['ARGONAUT_DEVELOPMENT']='1'
 os.environ['ARGONAUT_DEV_BUILD']=package_metadata['build']
if '--self-test' in sys.argv:
 import gi
 gi.require_version('Gtk','4.0');gi.require_version('Gst','1.0')
 from gi.repository import Gtk,Gio,Gst
 from c64u_browser.gui import Browser
 from c64u_browser.profiles import Preferences
 from c64u_browser.platform_support import publish_new,local_roots,portable_root
 from c64u_browser.credentials import Credentials
 root=portable_root()
 if root:
  config_name='argonaut-development' if package_metadata.get('development') else 'argonaut'
  assert Preferences().path == root/"Data"/config_name/"config.json"
  assert getattr(Credentials(),"session_only",False)
  prefs=Preferences();prefs.save();assert prefs.path.is_file()
 Gst.init(None)
 for name in ['appsrc','audioconvert','audioresample','autoaudiosink','webmmux','vp8enc','vorbisenc','videoconvert']:
  assert Gst.ElementFactory.find(name),name
 assert Gtk.init_check(),'GTK could not initialize'
 with tempfile.TemporaryDirectory() as d:
  app=Browser();app.preferences=Preferences(Path(d)/'config.json');app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None);app.activate()
  assert app.window and local_roots()
  from c64u_browser.about import show_about
  from c64u_browser.version import ASSETS,build_info
  assert (ASSETS/'about-background.png').is_file() and (ASSETS/'argonaut.png').is_file()
  expected_version='0.1.4-dev' if package_metadata.get('development') else package_metadata.get('version','0.1.4')
  assert build_info()['version']==expected_version and 'unpackaged' not in build_info()['build']
  if package_metadata.get('development'):
   assert Preferences().path.parent.name=='argonaut-development'
   assert getattr(Credentials(),'session_only',False)
   from c64u_browser.app_preferences import show_preferences
   preferences_dialog=show_preferences(app);assert preferences_dialog
   assert preferences_dialog.pages.get_n_pages()==3
   assert not preferences_dialog.connections.model.get_editable()
   assert preferences_dialog.connections.fields['case_edition'].get_editable()
   assert app.streams_tab.text_return.get_active()
   assert not app.streams_tab.zoom.get_editable()
   saved_scale=app.preferences.app_options['preview_scale']
   app.streams_tab.set_zoom(300);app.streams_tab.apply_scale()
   assert app.preferences.app_options['preview_scale']==saved_scale
   from c64u_browser.local_networks import local_networks
   assert isinstance(local_networks(),list)
   preferences_dialog.response(Gtk.ResponseType.CANCEL)
   assert app.lookup_action('quit').get_enabled()
  about=show_about(app);assert about is show_about(app);about.close();assert app.about_window is None
  app.activate_action('quit',None)
  assert app.window not in app.get_windows()
  src=Path(d)/'a';dst=Path(d)/'b';src.write_bytes(b'test');publish_new(src,dst);assert dst.read_bytes()==b'test'
 Path(sys.argv[sys.argv.index('--self-test')+1]).write_text(json.dumps({'result':'passed','platform':sys.platform}))
else:
 from c64u_browser.platform_support import portable_root
 root=portable_root()
 os.chdir(root or Path.home())
 from c64u_browser.gui import main
 main()
