#define MyAppName "CMClaw"
#define MyAppVersion "0.1.4.post4"
#define MyAppPublisher "Hss2019"
#define MyAppExeName "cmclaw.exe"
#define MySourceDir "..\dist\cmclaw"
#define MyIconFile "..\scripts\cmclaw.ico"

[Setup]
AppId={{7F5D6B5F-76D1-4C46-A6CC-61A5C7C6B123}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=CMClaw-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifexist "{#MyIconFile}"
SetupIconFile={#MyIconFile}
#endif

[Languages]
#ifexist "C:\Program Files (x86)\Inno Setup 6\Languages\ChineseSimplified.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifexist "{#MyIconFile}"
Source: "{#MyIconFile}"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
#ifexist "{#MyIconFile}"
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "desktop"; WorkingDir: "{app}"; IconFilename: "{app}\cmclaw.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "desktop"; WorkingDir: "{app}"; IconFilename: "{app}\cmclaw.ico"; Tasks: desktopicon
#else
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "desktop"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "desktop"; WorkingDir: "{app}"; Tasks: desktopicon
#endif

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "desktop"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
