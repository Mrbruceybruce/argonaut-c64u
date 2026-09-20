# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import platform
import json
root=Path(SPECPATH).parents[1]
build=json.loads((root/'c64u_browser/_build.json').read_text())
development=build.get('development',False)
version=build.get('version','1.5')
a=Analysis([str(root/'packaging/windows/launch.py')],pathex=[str(root)],
 datas=[(str(root/'c64u_browser/assets'),'c64u_browser/assets'),(str(root/'c64u_browser/_build.json'),'c64u_browser'),(str(root/'LICENSE'),'.'),(str(root/'COPYRIGHT'),'.')],
 hiddenimports=['gi.repository.Gtk','gi.repository.Gdk','gi.repository.Gst','gi.repository.GstPbutils','keyring.backends.macOS'],
 hooksconfig={'gi':{'module-versions':{'Gtk':'4.0','Gdk':'4.0'},'icons':['Adwaita'],'themes':['Adwaita']},
 'gstreamer':{'include_plugins':['coreelements','app','audioconvert','audioresample','autodetect','osxaudio','videoconvertscale','vpx','vorbis','ogg','matroska','multifile','typefindfunctions','playback','volume']}},
 excludes=['gi.repository.Secret'])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Argonaut',console=False,target_arch=platform.machine())
coll=COLLECT(exe,a.binaries,a.datas,name='Argonaut')
app=BUNDLE(coll,name='Argonaut Development.app' if development else 'Argonaut.app',icon=str(root/'packaging/icons/argonaut.icns'),bundle_identifier='org.argonaut.c64u.development' if development else 'org.argonaut.c64u',
 info_plist={'CFBundleShortVersionString':version,'CFBundleVersion':version,
 'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'15.0',
 'NSLocalNetworkUsageDescription':'Argonaut connects to your C64 Ultimate to manage files, settings, and screen preview.'})
