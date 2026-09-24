#ifndef AppVersion
#error AppVersion must be defined by the release pipeline
#endif
#ifndef AppNumericVersion
#error AppNumericVersion must be defined by the release pipeline
#endif
[Setup]
SetupIconFile=..\icons\argonaut.ico
AppId=Argonaut-C64U
AppName=Argonaut
AppVersion={#AppVersion}
VersionInfoVersion={#AppNumericVersion}
AppPublisher=Bruce Marcus
AppPublisherURL=https://github.com/Mrbruceybruce/argonaut-c64u
DefaultDirName={localappdata}\Programs\Argonaut
DefaultGroupName=Argonaut
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\release-assets
OutputBaseFilename=Argonaut-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Argonaut.exe
DisableProgramGroupPage=yes
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\..\dist\Argonaut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "portable.flag,Data\*"
[Icons]
Name: "{group}\Argonaut"; Filename: "{app}\Argonaut.exe"
Name: "{autodesktop}\Argonaut"; Filename: "{app}\Argonaut.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Argonaut.exe"; Description: "Launch Argonaut"; Flags: nowait postinstall skipifsilent
