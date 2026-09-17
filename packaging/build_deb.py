#!/usr/bin/python3
"""Build a Debian binary package using only Python and dpkg-deb."""
import argparse,os,shutil,subprocess,tempfile,json
from build_metadata import metadata
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,default=Path('dist'));p.add_argument('--version',default='1.5');p.add_argument('--development',action='store_true');args=p.parse_args()
source=args.source.resolve();assets=Path(__file__).resolve().parent;out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
version=args.version
app_name='argonaut-development' if args.development else 'argonaut'
package='argonaut-c64u-development' if args.development else 'argonaut-c64u'
build=metadata(source,version.replace('~','-'))
if args.development:build['development']=True
epoch=int(os.environ.get('SOURCE_DATE_EPOCH','1789240332'))
with tempfile.TemporaryDirectory(prefix='argonaut-deb-') as temp:
 root=Path(temp)
 def write(name,text,mode=0o644):
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);path.chmod(mode)
 for file in sorted((source/'c64u_browser').glob('*.py')):
  write(f'usr/lib/{app_name}/c64u_browser/'+file.name,file.read_text())
 shutil.copytree(source/'c64u_browser/assets',root/f'usr/lib/{app_name}/c64u_browser/assets')
 write(f'usr/lib/{app_name}/c64u_browser/_build.json',json.dumps(build))
 write(f'usr/bin/{app_name}', f'#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/{app_name}/launch.py "$@"\n',0o755)
 launch=('import json,os,sys\nfrom pathlib import Path\n'+
         ('os.environ["ARGONAUT_DEVELOPMENT"]="1"\n' if args.development else '')+
         f'sys.path.insert(0, "/usr/lib/{app_name}")\nimport c64u_browser\nmetadata_path=Path(c64u_browser.__file__).parent/"_build.json"\npackage_metadata=json.loads(metadata_path.read_text())\n'+
         'if "--self-test" in sys.argv:\n from c64u_browser.package_self_test import run\n run(package_metadata,sys.argv[sys.argv.index("--self-test")+1])\nelse:\n from c64u_browser.gui import main\n main()\n')
 write(f'usr/lib/{app_name}/launch.py',launch)
 if args.development:
  bridge_name=app_name+'-ai-bridge'
  write(f'usr/bin/{bridge_name}', f'#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/{app_name}/bridge.py "$@"\n',0o755)
  write(f'usr/lib/{app_name}/bridge.py', f'import os,sys\nos.environ["ARGONAUT_DEVELOPMENT"]="1"\nsys.path.insert(0, "/usr/lib/{app_name}")\nfrom c64u_browser.c64_ai_bridge_cli import main\nraise SystemExit(main())\n')
  unit=(source/'packaging/linux/argonaut-c64-ai-bridge.service').read_text()
  unit=unit.replace('@BRIDGE_EXECUTABLE@','/usr/bin/'+bridge_name)
  write('usr/lib/systemd/user/argonaut-c64-ai-bridge.service',unit)
  health_name=app_name+'-ai-health'
  write(f'usr/bin/{health_name}', f'#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/{app_name}/health.py "$@"\n',0o755)
  write(f'usr/lib/{app_name}/health.py', f'import os,sys\nos.environ["ARGONAUT_DEVELOPMENT"]="1"\nsys.path.insert(0, "/usr/lib/{app_name}")\nfrom c64u_browser.c64_ai_health_alert import main\nraise SystemExit(main())\n')
  health=(source/'packaging/linux/argonaut-c64-ai-health.service').read_text()
  health=health.replace('@HEALTH_EXECUTABLE@','/usr/bin/'+health_name)
  write('usr/lib/systemd/user/argonaut-c64-ai-health.service',health)
  write('usr/lib/systemd/user/argonaut-c64-ai-health.timer',
        (source/'packaging/linux/argonaut-c64-ai-health.timer').read_text())
  bridge_check_name=app_name+'-ai-bridge-check'
  write(f'usr/bin/{bridge_check_name}', f'#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/{app_name}/bridge_check.py "$@"\n',0o755)
  write(f'usr/lib/{app_name}/bridge_check.py', f'import os,sys\nos.environ["ARGONAUT_DEVELOPMENT"]="1"\nsys.path.insert(0, "/usr/lib/{app_name}")\nfrom c64u_browser.c64_ai_bridge_check import main\nraise SystemExit(main())\n')
  alert_name=app_name+'-test-lab-alert'
  write(f'usr/bin/{alert_name}', f'#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/{app_name}/alert.py "$@"\n',0o755)
  write(f'usr/lib/{app_name}/alert.py', f'import os,sys\nos.environ["ARGONAUT_DEVELOPMENT"]="1"\nsys.path.insert(0, "/usr/lib/{app_name}")\nfrom c64u_browser.test_lab_alert import main\nraise SystemExit(main())\n')
  fleet=(source/'packaging/linux/argonaut-test-lab-fleet.service').read_text()
  fleet=fleet.replace('@ALERT_EXECUTABLE@','/usr/bin/'+alert_name)
  write('usr/lib/systemd/user/argonaut-test-lab-fleet.service',fleet)
  write('usr/lib/systemd/user/argonaut-test-lab-fleet.timer',
        (source/'packaging/linux/argonaut-test-lab-fleet.timer').read_text())
 desktop=(assets/'desktop/argonaut.desktop').read_text().replace('Exec=argonaut','Exec='+app_name).replace('Icon=argonaut','Icon='+app_name)
 if args.development:desktop=desktop.replace('Name=Argonaut','Name=Argonaut Development '+version.replace('~','-'))
 write(f'usr/share/applications/{app_name}.desktop',desktop)
 for size in (16,24,32,48,64,128,256,512,1024):
  destination=root/f'usr/share/icons/hicolor/{size}x{size}/apps/{app_name}.png'
  destination.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(assets/f'icons/argonaut-{size}.png',destination)
 for name in ['README.md','LICENSE','COPYRIGHT']:
  write(f'usr/share/doc/{package}/'+name,(source/name).read_text())
 write(f'usr/share/doc/{package}/RELEASE-NOTES.md',(assets/'RELEASE-NOTES.md').read_text())
 write(f'usr/share/doc/{package}/copyright',(source/'COPYRIGHT').read_text() + '\nLicense: GPL-3.0-or-later. Full license: LICENSE in this directory.\n')
 size=sum(f.stat().st_size for f in root.rglob('*') if f.is_file())//1024+1
 write('DEBIAN/control',f'''Package: {package}
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: Bruce Marcus <argonaut@localhost>
Installed-Size: {size}
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0 (>= 4.8), gir1.2-secret-1, gir1.2-gstreamer-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, iproute2, adwaita-icon-theme
Recommends: gnome-keyring
Suggests: ollama
Description: GTK desktop controller and file manager for C64 Ultimate
 Manage connection profiles, USB and SD files, settings, ROMs,
 configuration backups, screen preview, screenshots and recordings.
 Built and tested on Debian 13 with GTK 4.
''')
 for f in root.rglob('*'):os.utime(f,(epoch,epoch))
 subprocess.run(['dpkg-deb','--root-owner-group','--build',str(root),str(out/f'{package}_{version}_all.deb')],check=True,env={**os.environ,'SOURCE_DATE_EPOCH':str(epoch)})
