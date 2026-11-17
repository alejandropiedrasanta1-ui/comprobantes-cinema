# Arma el instalador de Windows (mismo método que CineSlide): compila instalador_windows.cs con el csc.exe de
# .NET Framework (viene con Windows) y le pega al final el programa comprimido en .zip.
#   pwsh -File construir_instalador.ps1 -Dist "<carpeta dist\Comprobantes Cinema>" -Salida "<carpeta INSTALADOR>"
# Resultado: "<Salida>\Instalar Comprobantes Cinema (Windows) <versión>.exe"
param(
    [string]$Dist = (Join-Path $PSScriptRoot "..\dist\Comprobantes Cinema"),
    [string]$Salida = (Join-Path $PSScriptRoot "..\..\..\INSTALADOR")
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem

$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path          # PROGRAMA
$Dist = (Resolve-Path $Dist).Path
if (-not (Test-Path (Join-Path $Dist "Comprobantes Cinema.exe"))) { throw "No está el programa compilado en $Dist" }
New-Item -ItemType Directory -Force $Salida | Out-Null
$Salida = (Resolve-Path $Salida).Path
$version = [regex]::Match((Get-Content (Join-Path $raiz "rutas.py") -Raw), 'VERSION\s*=\s*"([^"]+)"').Groups[1].Value
if (-not $version) { throw "No se encontró VERSION en rutas.py" }

$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
if (-not (Test-Path $csc)) { throw "No se encontró csc.exe de .NET Framework 4" }

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("comprobantes-instalador-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory $tmp | Out-Null
try {
    # 1) versión y datos del archivo (Propiedades > Detalles)
    $versionCs = @"
using System.Reflection;
[assembly: AssemblyTitle("Instalar Comprobantes Cinema")]
[assembly: AssemblyDescription("Instalador de Comprobantes Cinema Productions")]
[assembly: AssemblyCompany("Cinema Productions")]
[assembly: AssemblyProduct("Comprobantes Cinema Productions")]
[assembly: AssemblyCopyright("Cinema Productions")]
[assembly: AssemblyVersion("$version.0")]
[assembly: AssemblyFileVersion("$version.0")]
[assembly: AssemblyInformationalVersion("$version")]
static class VersionApp { public const string V = "$version"; }
"@
    [IO.File]::WriteAllText((Join-Path $tmp "version.cs"), $versionCs, [Text.UTF8Encoding]::new($true))

    # 2) ícono de la ventana (256 px) a partir de recursos\icono.png
    $png = Join-Path $tmp "icono.png"
    $py = "from PIL import Image; import sys; Image.open(sys.argv[1]).convert('RGBA').resize((256,256), Image.LANCZOS).save(sys.argv[2])"
    python -c $py (Join-Path $raiz "recursos\icono.png") $png
    if ($LASTEXITCODE -or -not (Test-Path $png)) { Copy-Item (Join-Path $raiz "recursos\icono.png") $png }

    # 3) compilar (C# 5, .NET Framework 4)
    $exe = Join-Path $tmp "instalador.exe"
    $refs = "System.dll", "System.Core.dll", "System.Drawing.dll", "System.Windows.Forms.dll", "System.IO.Compression.dll",
            "System.IO.Compression.FileSystem.dll", "Microsoft.CSharp.dll" | ForEach-Object { "/r:$_" }
    & $csc /nologo /target:winexe /optimize+ /platform:anycpu /codepage:65001 `
        "/win32icon:$(Join-Path $raiz 'recursos\icono.ico')" "/resource:$png,icono.png" @refs `
        "/out:$exe" (Join-Path $PSScriptRoot "instalador_windows.cs") (Join-Path $tmp "version.cs")
    if ($LASTEXITCODE) { throw "csc no pudo compilar el instalador" }

    # 4) el programa en .zip
    $zip = Join-Path $tmp "paquete.zip"
    [IO.Compression.ZipFile]::CreateFromDirectory($Dist, $zip, [IO.Compression.CompressionLevel]::Optimal, $false)

    # 5) [instalador.exe][paquete.zip][posición Int64][CCPAQ001]
    $destino = Join-Path $Salida "Instalar Comprobantes Cinema (Windows) $version.exe"
    $exeBytes = [IO.File]::ReadAllBytes($exe)
    $sal = [IO.File]::Create($destino)
    try {
        $sal.Write($exeBytes, 0, $exeBytes.Length)
        $z = [IO.File]::OpenRead($zip)
        try { $z.CopyTo($sal) } finally { $z.Dispose() }
        $pie = [byte[]]([BitConverter]::GetBytes([long]$exeBytes.Length) + [Text.Encoding]::ASCII.GetBytes("CCPAQ001"))
        $sal.Write($pie, 0, $pie.Length)
    } finally { $sal.Dispose() }
    Write-Host ("Listo: {0} ({1:N0} MB)" -f $destino, ((Get-Item $destino).Length / 1MB))
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
