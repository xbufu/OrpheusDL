#define MyAppName "OrpheusDL"
#include "version.iss"
#define MyAppPublisher "OrpheusDL"
#define MyAppURL "https://github.com/xbufu/OrpheusDL"
#define MyAppExeName "OrpheusDL.exe"
#define SourcePath "..\..\dist\OrpheusDL"
#define RepoDir "..\.."

[Setup]
AppId={{B3C4D5E6-F7A8-9012-BCDE-F01234567891}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\OrpheusDL
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#MyAppName}
OutputDir=..\..\dist
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}



Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
AllowNoIcons=yes
DisableProgramGroupPage=yes
CloseApplications=force

[Types]
Name: "full"; Description: "Full installation"
Name: "compact"; Description: "Compact installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "main"; Description: "OrpheusDL Core (required)"; Types: full compact custom; Flags: fixed
Name: "ffmpeg"; Description: "FFmpeg (required for codec conversions)"; Types: full custom; Flags: fixed

Name: "modules"; Description: "Music Platform Modules"; Types: full custom
Name: "modules\example"; Description: "Example support"; Types: full custom
Name: "modules\beatport"; Description: "Beatport support"; Types: full custom


[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourcePath}\{#MyAppExeName}"; DestDir: "{app}"; Components: main; Flags: ignoreversion
Source: "{#SourcePath}\*"; Excludes: "{#MyAppExeName}"; DestDir: "{app}"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#SourcePath}\config\settings.json"; DestDir: "{app}\config"; Components: main; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "{#RepoDir}\bin\ffmpeg.exe"; DestDir: "{app}"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#RepoDir}\bin\ffprobe.exe"; DestDir: "{app}"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist

Source: "{#RepoDir}\modules\example\*"; DestDir: "{app}\modules\example"; Components: modules\example; Flags: recursesubdirs
Source: "{#RepoDir}\modules\beatport\*"; DestDir: "{app}\modules\beatport"; Components: modules\beatport; Flags: recursesubdirs

Source: "{#RepoDir}\modules\__init__.py"; DestDir: "{app}\modules"; Components: main; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\OrpheusDL.exe"; Description: "{cm:LaunchProgram,OrpheusDL}"; Flags: nowait postinstall skipifsilent

