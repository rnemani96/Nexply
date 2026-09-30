; ============================================================
; RAJESH AI — Windows Installer Script (Inno Setup 6)
; Compile with Inno Setup 6: https://jrsoftware.org/isinfo.php
; Output: dist/installer/RajeshAI_Setup_v3.0.exe
; ============================================================

#define AppName "RAJESH AI"
#define AppVersion "3.0.0"
#define AppPublisher "Rajesh"
#define AppURL "https://github.com/rnemani96/RajeshAI"
#define AppExeName "RajeshAI.exe"
#define AppDescription "Autonomous Job Applier"

[Setup]
AppId={{6A4F2B8C-1D3E-4F7A-9B2C-5E8D0A3F6C1B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Output
OutputDir=dist\installer
OutputBaseFilename=RajeshAI_Setup_v{#AppVersion}
; UI
WizardStyle=modern
WizardResizable=yes
; Icon (use our custom icon if it exists)
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
; Min Windows 10
MinVersion=10.0
; 64-bit only
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Privacy
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
; Require no elevation (installs per-user by default, can be system-wide)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";     Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon";     Description: "Start {#AppName} with Windows (system tray)"; GroupDescription: "Startup:"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main application (the entire dist\RajeshAI folder)
Source: "dist\RajeshAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Documentation
Source: "docs\RAJESH_AI_Documentation.docx"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist

; Default config (only if user hasn't already configured)
Source: "config\settings.yaml"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist

[Dirs]
; Create writable user-data directories next to install
Name: "{app}\data"
Name: "{app}\resume\generated"
Name: "{app}\output"
Name: "{app}\logs"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "{#AppDescription}"
Name: "{autoprograms}\{#AppName}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; Comment: "{#AppDescription}"
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Registry]
; Add to Windows startup (system tray mode) if user selected that task
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Open the app after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill the process before uninstall
Filename: "taskkill"; Parameters: "/f /im {#AppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillApp"

[Code]
// Show a friendly welcome message about first-time setup
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption :=
    'This will install ' + '{#AppName}' + ' version ' + '{#AppVersion}' + ' on your computer.' + #13#10 + #13#10 +
    'FIRST-TIME SETUP after install:' + #13#10 +
    '  1. Copy your resume to: install_dir\resume\master_resume.docx' + #13#10 +
    '  2. Get a free AI key: https://console.groq.com (Groq) or' + #13#10 +
    '     https://aistudio.google.com (Gemini)' + #13#10 +
    '  3. Or install Ollama (offline AI): https://ollama.com' + #13#10 + #13#10 +
    'Click Next to continue.';
end;
