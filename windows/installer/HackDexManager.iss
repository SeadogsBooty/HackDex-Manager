#define MyAppName "HackDex Manager"
#define MyAppVersion "1.1.2"
#define MyAppPublisher "HackDex Manager"
#define MyAppExeName "HackDex Manager.exe"

[Setup]
AppId={{9FBD4D7B-5D5E-4DAE-9EA9-3F46E2C7BA34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={%USERPROFILE}\HackDex-Manager
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=HackDex Manager Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSmallImageFile=..\assets\installer-small.bmp
WizardImageFile=..\assets\installer-large.bmp
SetupIconFile=..\assets\HackDexManager.ico
LicenseFile=..\..\LICENSE
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\HackDex Manager\HackDex Manager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\HackDex Manager\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\Data"; Flags: uninsneveruninstall
Name: "{app}\Staging"; Flags: uninsneveruninstall
Name: "{app}\Logs"; Flags: uninsneveruninstall
Name: "{app}\Backups"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\HackDex Manager"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\HackDex Manager"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch HackDex Manager"; Flags: nowait postinstall skipifsilent
