#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifdef ValidationBuild
  #define AppName "Cloud Hub Verification"
  #define ProductId "33D58E9E-E275-41E8-8BC2-BB9CFD0CF308"
#else
  #define AppName "Nelviro"
  #define ProductId "FC837952-6ABC-4F61-8A70-1ED23D0FD195"
#endif
#define AppUrl "https://github.com/BochkaPiva/dinamic_island_windows"

[Setup]
AppId={{{#ProductId}}
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
UninstallDisplayIcon={app}\_internal\island\assets\brand\Nelviro.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=force
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=Output
OutputBaseFilename=Nelviro-Setup-{#AppVersion}-win-x64

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\CloudIsland\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"
Source: "..\THIRD_PARTY.md"; DestDir: "{app}"
Source: "..\build\licenses\*"; DestDir: "{app}\licenses"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\CloudIsland.exe"; IconFilename: "{app}\_internal\island\assets\brand\Nelviro.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\CloudIsland.exe"; IconFilename: "{app}\_internal\island\assets\brand\Nelviro.ico"; Check: WantDesktopShortcut

[InstallDelete]
; Application runtime contains no user data. Never retain plugins from a previous Qt.
Type: filesandordirs; Name: "{app}\_internal"
#ifndef ValidationBuild
Type: files; Name: "{autoprograms}\Cloud Hub.lnk"; Check: OwnedShortcut('{autoprograms}\Cloud Hub.lnk')
Type: files; Name: "{autodesktop}\Cloud Hub.lnk"; Check: OwnedShortcut('{autodesktop}\Cloud Hub.lnk')
Type: files; Name: "{autoprograms}\Cloud Island.lnk"; Check: OwnedShortcut('{autoprograms}\Cloud Island.lnk')
Type: files; Name: "{autodesktop}\Cloud Island.lnk"; Check: OwnedShortcut('{autodesktop}\Cloud Island.lnk')
#endif

[Run]
Filename: "{app}\CloudIsland.exe"; Description: "{cm:LaunchProgram,Nelviro}"; Flags: nowait postinstall skipifsilent

[Code]
var
  PreserveDesktopShortcut: Boolean;

function OwnedShortcut(Path: String): Boolean;
var
  Shell, Link: Variant;
begin
  Result := False;
  if not FileExists(ExpandConstant(Path)) then exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(ExpandConstant(Path));
    Result := CompareText(Link.TargetPath, ExpandConstant('{app}\CloudIsland.exe')) = 0;
  except
    Result := False;
  end;
end;

function WantDesktopShortcut: Boolean;
begin
  Result := WizardIsTaskSelected('desktopicon') or PreserveDesktopShortcut;
end;

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
  PreserveDesktopShortcut := OwnedShortcut('{autodesktop}\Cloud Hub.lnk') or
    OwnedShortcut('{autodesktop}\Cloud Island.lnk') or OwnedShortcut('{autodesktop}\Nelviro.lnk');
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
#ifndef ValidationBuild
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Cloud Island');
#endif
end;
