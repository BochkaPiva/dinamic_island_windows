#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Cloud Hub"
#define AppUrl "https://github.com/BochkaPiva/dinamic_island_windows"

[Setup]
AppId={{FC837952-6ABC-4F61-8A70-1ED23D0FD195}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BochkaPiva
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases/latest
DefaultDirName={localappdata}\Programs\Cloud Island
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
SetupIconFile=cloud.ico
UninstallDisplayIcon={app}\CloudIsland.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=force
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=Output
OutputBaseFilename=CloudIsland-Setup-{#AppVersion}-win-x64

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\CloudIsland.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"
Source: "..\THIRD_PARTY.md"; DestDir: "{app}"
Source: "..\build\licenses\*"; DestDir: "{app}\licenses"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Cloud Hub"; Filename: "{app}\CloudIsland.exe"
Name: "{autodesktop}\Cloud Hub"; Filename: "{app}\CloudIsland.exe"; Tasks: desktopicon

[InstallDelete]
Type: files; Name: "{autoprograms}\Cloud Island.lnk"
Type: files; Name: "{autodesktop}\Cloud Island.lnk"

[Run]
Filename: "{app}\CloudIsland.exe"; Description: "{cm:LaunchProgram,Cloud Hub}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CloseIsland;
var
  ResultCode: Integer;
begin
  if FileExists(ExpandConstant('{app}\CloudIsland.exe')) then begin
    Exec(ExpandConstant('{app}\CloudIsland.exe'), '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(500);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CloseIsland;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  CloseIsland;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Cloud Island');
end;
