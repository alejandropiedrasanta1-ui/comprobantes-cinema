# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para Windows (carpeta con .exe) y Mac (.app).
# Se usa desde "CREAR INSTALADOR WINDOWS.bat" o "CREAR APP MAC.command".
import re
import sys
from pathlib import Path

RAIZ = Path(SPECPATH).parent
ES_MAC = sys.platform == "darwin"
NOMBRE = "Comprobantes Cinema"
VERSION = re.search(r'VERSION\s*=\s*"([^"]+)"', (RAIZ / "rutas.py").read_text(encoding="utf-8")).group(1)

datas = [
    (str(RAIZ / "config_default.json"), "."),
    (str(RAIZ / "recursos" / "icono.png"), "recursos"),
    (str(RAIZ / "recursos" / "ilustracion_vacio.png"), "recursos"),
    (str(RAIZ / "recursos" / "iconos"), "recursos/iconos"),   # íconos de la interfaz (Higgsfield)
    (str(RAIZ / "recursos" / "ilustracion_vacio_claro.png"), "recursos"),
]
# Las fuentes del diseño (recursos/fuentes, también en el repositorio: van en Windows y en Mac)
if any((RAIZ / "recursos" / "fuentes").glob("*.*")):
    datas.append((str(RAIZ / "recursos" / "fuentes"), "recursos/fuentes"))
datas += [(str(p), "PLANTILLAS") for p in sorted((RAIZ / "PLANTILLAS").glob("*.psd"))]
datas += [(str(p), "PLANTILLAS") for p in sorted((RAIZ / "PLANTILLAS").glob("*.json"))]   # medidas de la lista
datas += [(str(p), "PLANTILLAS") for p in sorted((RAIZ / "PLANTILLAS").glob("VISTA PREVIA*.jpg"))]

a = Analysis(
    [str(RAIZ / "generador.py")],
    pathex=[str(RAIZ)],
    datas=datas,
    # scipy/numpy/colorthief: solo para el efecto acrílico opcional de Fluent-Widgets (no se usa)
    excludes=["tkinter", "crear_plantillas", "scipy", "numpy", "colorthief"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icono = str(RAIZ / "recursos" / ("icono.png" if ES_MAC else "icono.ico"))

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOMBRE,
    console=False,
    icon=icono,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NOMBRE)

if ES_MAC:
    app = BUNDLE(
        coll,
        name=f"{NOMBRE}.app",
        icon=icono,
        bundle_identifier="com.cinemaproductions.comprobantes",
        info_plist={
            "CFBundleDisplayName": "Comprobantes Cinema Productions",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
