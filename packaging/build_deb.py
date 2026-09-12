#!/usr/bin/python3
"""Build a Debian binary package using only Python and dpkg-deb."""
import argparse,os,shutil,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,default=Path('dist'));p.add_argument('--version',default='0.1.0');args=p.parse_args()
source=args.source.resolve();assets=Path(__file__).resolve().parent;out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
version=args.version;epoch=int(os.environ.get('SOURCE_DATE_EPOCH','1789240332'))
with tempfile.TemporaryDirectory(prefix='argonaut-deb-') as temp:
 root=Path(temp)
 def write(name,text,mode=0o644):
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);path.chmod(mode)
 for file in sorted((source/'c64u_browser').glob('*.py')):
  write('usr/lib/argonaut/c64u_browser/'+file.name,file.read_text())
 write('usr/bin/argonaut', '#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/argonaut/launch.py "$@"\n',0o755)
 write('usr/lib/argonaut/launch.py', 'import sys\nsys.path.insert(0, "/usr/lib/argonaut")\nfrom c64u_browser.gui import main\nmain()\n')
 write('usr/share/applications/argonaut.desktop',(assets/'desktop/argonaut.desktop').read_text())
 write('usr/share/icons/hicolor/scalable/apps/argonaut.svg',(assets/'desktop/argonaut.svg').read_text())
 for name in ['README.md','LICENSE','COPYRIGHT']:
  write('usr/share/doc/argonaut-c64u/'+name,(source/name).read_text())
 write('usr/share/doc/argonaut-c64u/RELEASE-NOTES.md',(assets/'RELEASE-NOTES.md').read_text())
 write('usr/share/doc/argonaut-c64u/copyright',(source/'COPYRIGHT').read_text() + '\nLicense: GPL-3.0-or-later. Full license: LICENSE in this directory.\n')
 size=sum(f.stat().st_size for f in root.rglob('*') if f.is_file())//1024+1
 write('DEBIAN/control',f'''Package: argonaut-c64u
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: Bruce Marcus <argonaut@localhost>
Installed-Size: {size}
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0 (>= 4.8), gir1.2-secret-1, gir1.2-gstreamer-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, iproute2, adwaita-icon-theme
Recommends: gnome-keyring
Description: GTK desktop controller and file manager for C64 Ultimate
 Manage connection profiles, USB and SD files, settings, ROMs,
 configuration backups, screen preview, screenshots and recordings.
 Built and tested on Debian 13 with GTK 4.
''')
 for f in root.rglob('*'):os.utime(f,(epoch,epoch))
 subprocess.run(['dpkg-deb','--root-owner-group','--build',str(root),str(out/f'argonaut-c64u_{version}_all.deb')],check=True,env={**os.environ,'SOURCE_DATE_EPOCH':str(epoch)})
