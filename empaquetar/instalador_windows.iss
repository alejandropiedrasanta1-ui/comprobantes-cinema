; Instalador de Windows de UN CLIC (Inno Setup 6). Se compila con "CREAR INSTALADOR WINDOWS.bat".
; Doble clic -> solo la barra de progreso -> instala, crea accesos directos, abre el programa y se cierra.
#define AppName "Comprobantes Cinema Productions"
#define AppVersion "2.1.0"
#define AppExe "Comprobantes Cinema.exe"

[Setup]
AppId={{4F5098BC-D578-40A3-8BDB-5CCAD9D12264}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Cinema Productions
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Sin pantallas: ni bienvenida, ni carpeta, ni "listo para instalar", ni "terminado"
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
ShowLanguageDialog=no
; Para el usuario actual: no pide permisos de administrador
PrivilegesRequired=lowest
; Si el programa está abierto (actualización), se cierra solo
CloseApplications=force
RestartApplications=no
OutputDir=..\..\INSTALADOR
OutputBaseFilename=Instalar Comprobantes Cinema (Windows) {#AppVersion}
SetupIconFile=..\recursos\icono.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=100
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "dist\Comprobantes Cinema\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Fuentes del diseño (solo para el usuario; no se quitan al desinstalar porque otros programas pueden usarlas)
Source: "..\recursos\fuentes\LEMONMILK-Bold.otf"; DestDir: "{autofonts}"; FontInstall: "LEMON MILK Bold (OpenType)"; Flags: onlyifdoesntexist uninsneveruninstall fontisnttruetype
Source: "..\recursos\fuentes\GetVoIP Grotesque.otf"; DestDir: "{autofonts}"; FontInstall: "GetVoIP Grotesque (OpenType)"; Flags: onlyifdoesntexist uninsneveruninstall fontisnttruetype
Source: "..\recursos\fuentes\MYRIADPRO-BOLD.OTF"; DestDir: "{autofonts}"; FontInstall: "Myriad Pro Bold (OpenType)"; Flags: onlyifdoesntexist uninsneveruninstall fontisnttruetype
Source: "..\recursos\fuentes\MYRIADPRO-REGULAR.OTF"; DestDir: "{autofonts}"; FontInstall: "Myriad Pro Regular (OpenType)"; Flags: onlyifdoesntexist uninsneveruninstall fontisnttruetype

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
; Al terminar abre el programa (si falta PhotoCraft, el programa mismo lo avisa)
Filename: "{app}\{#AppExe}"; Flags: nowait skipifsilent
