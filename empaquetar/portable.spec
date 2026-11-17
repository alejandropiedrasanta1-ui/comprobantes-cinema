# -*- mode: python ; coding: utf-8 -*-
# Versión PORTABLE: un solo .exe que no se instala. Guarda ajustes y comprobantes junto al .exe.
# Se usa desde "CREAR INSTALADOR WINDOWS.bat".
from pathlib import Path

RAIZ = Path(SPECPATH).parent

datas = [
    (str(RAIZ / "config_default.json"), "."),
    (str(RAIZ / "empaquetar" / "portable.flag"), "."),
    (str(RAIZ / "recursos" / "icono.png"), "recursos"),
    (str(RAIZ / "recursos" / "ilustracion_vacio.png"), "recursos"),
    (str(RAIZ / "recursos" / "iconos"), "recursos/iconos"),
]
# Las fuentes van incluidas solo si están en la carpeta (en GitHub no se publican por licencia)
if any((RAIZ / "recursos" / "fuentes").glob("*.*")):
    datas.append((str(RAIZ / "recursos" / "fuentes"), "recursos/fuentes"))
datas += [(str(p), "PLANTILLAS") for p in sorted((RAIZ / "PLANTILLAS").glob("*.psd"))]
datas += [(str(p), "PLANTILLAS") for p in sorted((RAIZ / "PLANTILLAS").glob("VISTA PREVIA - *.jpg"))]

a = Analysis(
    [str(RAIZ / "generador.py")],
    pathex=[str(RAIZ)],
    datas=datas,
    # scipy/numpy/colorthief: solo para el efecto acrílico opcional de Fluent-Widgets (no se usa)
    excludes=["tkinter", "crear_plantillas", "scipy", "numpy", "colorthief"],
)
splash = Splash(
    str(RAIZ / "recursos" / "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(20, 340),
    text_size=9,
    text_color="#777777",
    minify_script=True,
    always_on_top=True,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name="Comprobantes Cinema Portable",
    console=False,
    icon=str(RAIZ / "recursos" / "icono.ico"),
    upx=False,
)
