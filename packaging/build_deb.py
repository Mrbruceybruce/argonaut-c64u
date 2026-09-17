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
 identity='os.environ["ARGONAUT_DEVELOPMENT"]="1"\n' if args.development else ''
 def tool(script,module,name):
  executable=app_name+'-'+name
  write(f'usr/bin/{executable}', f'#!/bin/sh\ncd "$HOME" || exit 1\nexec /usr/bin/python3 -I /usr/lib/{app_name}/{script}.py "$@"\n',0o755)
  write(f'usr/lib/{app_name}/{script}.py', f'import os,sys\n{identity}sys.path.insert(0, "/usr/lib/{app_name}")\nfrom c64u_browser.{module} import main\nraise SystemExit(main())\n')
  return executable
 config_name=app_name
 development_env='Environment=ARGONAUT_DEVELOPMENT=1' if args.development else ''
 bridge_name=tool('bridge','c64_ai_bridge_cli','ai-bridge')
 bridge_unit=app_name+'-c64-ai-bridge.service'
 unit=(source/'packaging/linux/argonaut-c64-ai-bridge.service').read_text()
 unit=unit.replace('@BRIDGE_EXECUTABLE@','/usr/bin/'+bridge_name)
 write('usr/lib/systemd/user/'+bridge_unit,unit)
 health_name=tool('health','c64_ai_health_alert','ai-health')
 health_unit=app_name+'-c64-ai-health.service'
 health=(source/'packaging/linux/argonaut-c64-ai-health.service').read_text()
 health=health.replace('@HEALTH_EXECUTABLE@','/usr/bin/'+health_name).replace('@CONFIG_NAME@',config_name).replace('@DEVELOPMENT_ENV@',development_env)
 write('usr/lib/systemd/user/'+health_unit,health)
 health_timer=(source/'packaging/linux/argonaut-c64-ai-health.timer').read_text().replace('@SERVICE_UNIT@',health_unit)
 write('usr/lib/systemd/user/'+app_name+'-c64-ai-health.timer',health_timer)
 tool('bridge_check','c64_ai_bridge_check','ai-bridge-check')
 ai_test_name=tool('ai_test_alert','c64_ai_bridge_alert','ai-test-alert')
 ai_test_unit=app_name+'-c64-ai-test.service'
 ai_test=(source/'packaging/linux/argonaut-c64-ai-test.service').read_text()
 ai_test=ai_test.replace('@AI_TEST_EXECUTABLE@','/usr/bin/'+ai_test_name).replace('@CONFIG_NAME@',config_name).replace('@DEVELOPMENT_ENV@',development_env)
 write('usr/lib/systemd/user/'+ai_test_unit,ai_test)
 ai_test_timer=(source/'packaging/linux/argonaut-c64-ai-test.timer').read_text().replace('@SERVICE_UNIT@',ai_test_unit)
 write('usr/lib/systemd/user/'+app_name+'-c64-ai-test.timer',ai_test_timer)
 alert_name=tool('alert','test_lab_alert','test-lab-alert')
 fleet_unit=app_name+'-test-lab-fleet.service'
 fleet=(source/'packaging/linux/argonaut-test-lab-fleet.service').read_text()
 fleet=fleet.replace('@ALERT_EXECUTABLE@','/usr/bin/'+alert_name).replace('@CONFIG_NAME@',config_name).replace('@DEVELOPMENT_ENV@',development_env)
 write('usr/lib/systemd/user/'+fleet_unit,fleet)
 fleet_timer=(source/'packaging/linux/argonaut-test-lab-fleet.timer').read_text().replace('@SERVICE_UNIT@',fleet_unit)
 write('usr/lib/systemd/user/'+app_name+'-test-lab-fleet.timer',fleet_timer)
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
