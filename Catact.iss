; -*- coding: utf-8 -*-
; Catact 安装包脚本

[Setup]
AppId={{7E2A9C41-5B3D-4F8A-9C6E-1D24A8B3F5C7}
AppName=Catact
AppVersion=1.0.6
AppVerName=Catact 1.0.6
DefaultDirName={localappdata}\Catact
DefaultGroupName=Catact
PrivilegesRequired=lowest
SetupIconFile=app\catact.ico
UninstallDisplayIcon={app}\Catact.exe
OutputDir=installer
OutputBaseFilename=Catact_Setup_1.0.6
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
CloseApplicationsFilter=Catact.exe

[Languages]
Name: "chs"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
Source: "release\Catact\Catact.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\Catact\catact.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\Catact\mx_bridge.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\Catact\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\Catact\python32\*"; DestDir: "{app}\python32"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Catact"; Filename: "{app}\Catact.exe"; IconFilename: "{app}\catact.ico"
Name: "{group}\卸载 Catact"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Catact"; Filename: "{app}\Catact.exe"; IconFilename: "{app}\catact.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Catact.exe"; Description: "立即运行 Catact"; Flags: nowait postinstall skipifsilent
