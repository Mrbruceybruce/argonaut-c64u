# SPDX-License-Identifier: GPL-3.0-or-later
import os,sys,tempfile,json
from pathlib import Path
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
  assert Preferences().path == root/"Data"/"argonaut"/"config.json"
  assert getattr(Credentials(),"session_only",False)
  prefs=Preferences();prefs.save();assert prefs.path.is_file()
 Gst.init(None)
 for name in ['appsrc','audioconvert','audioresample','autoaudiosink','webmmux','vp8enc','vorbisenc','videoconvert']:
  assert Gst.ElementFactory.find(name),name
 assert Gtk.init_check(),'GTK could not initialize'
 with tempfile.TemporaryDirectory() as d:
  app=Browser();app.preferences=Preferences(Path(d)/'config.json');app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None);app.activate()
  assert app.window and local_roots()
  app.recovery.close();app.window.close();app.quit()
  src=Path(d)/'a';dst=Path(d)/'b';src.write_bytes(b'test');publish_new(src,dst);assert dst.read_bytes()==b'test'
 Path(sys.argv[sys.argv.index('--self-test')+1]).write_text(json.dumps({'result':'passed','platform':sys.platform}))
else:
 from c64u_browser.platform_support import portable_root
 root=portable_root()
 os.chdir(root or Path.home())
 from c64u_browser.gui import main
 main()
