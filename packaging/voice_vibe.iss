; Voice Vibe Windows 安装包脚本（Inno Setup 6）
; 先用 packaging\build_exe.bat 生成 dist\VoiceVibe\，再运行本脚本生成安装包：
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\voice_vibe.iss

#define MyAppName "Voice Vibe"
#define MyAppNameZh "Voice Vibe 语音输入"
#define MyAppVersion "0.1.0"
#define MyAppExeName "VoiceVibe.exe"

[Setup]
AppId={{09AFCC74-FAE1-471A-A93C-EA2EBBD6E4F2}
AppName={#MyAppNameZh}
AppVersion={#MyAppVersion}
AppVerName={#MyAppNameZh} {#MyAppVersion}
AppPublisher=Voice Vibe
DefaultDirName={autopf}\VoiceVibe
DefaultGroupName={#MyAppNameZh}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=VoiceVibe-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
; 安装包本身含简体中文文本，需要 Unicode 版 Inno Setup（6.x 默认即是）
ShowLanguageDialog=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\VoiceVibe\VoiceVibe.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\VoiceVibe\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppNameZh}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppNameZh}}"; Flags: nowait postinstall skipifsilent

[Code]
// 安装/卸载前结束正在运行的实例，避免文件被占用导致覆盖失败
procedure KillRunningInstance;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im {#MyAppExeName} /t', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(300);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  KillRunningInstance;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    KillRunningInstance;
end;
