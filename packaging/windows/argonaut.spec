# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
root=Path(SPECPATH).parents[1]
licenses=Path(sys.prefix)/'share/licenses'
datas=[(str(root/'LICENSE'),'.'),(str(root/'COPYRIGHT'),'.'),(str(root/'packaging/windows/README.txt'),'.')]
if licenses.exists():datas.append((str(licenses),'third-party-licenses'))
a=Analysis([str(root/'packaging/windows/launch.py')],pathex=[str(root)],datas=datas,
 hiddenimports=['gi.repository.Gtk','gi.repository.Gdk','gi.repository.Gst'],
 hooksconfig={'gi':{'module-versions':{'Gtk':'4.0','Gdk':'4.0'},'icons':['Adwaita'],'themes':['Adwaita']},
 'gstreamer':{'include_plugins':['coreelements','app','audioconvert','audioresample','autodetect','directsound','wasapi','wasapi2','videoconvertscale','vpx','vorbis','ogg','matroska','typefindfunctions','playback','volume']}},
 excludes=['gi.repository.Secret'])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Argonaut',console=False)
coll=COLLECT(exe,a.binaries,a.datas,name='Argonaut')
