"""Instala (solo para el usuario actual) las fuentes del diseño si PhotoCraft no las encuentra.

Las fuentes vienen dentro del programa (recursos/fuentes, también en el repositorio y en el .dmg
de Mac). Además se pueden instalar eligiendo la carpeta donde están: instalar_desde(carpeta)."""
import shutil
from pathlib import Path

import rutas

# Familia (como la ve PhotoCraft) -> archivos esperados
FUENTES = {
    "LEMON MILK": ["LEMONMILK-Bold.otf"],
    "GetVoIP Grotesque": ["GetVoIP Grotesque.otf"],
    "Myriad Pro": ["MYRIADPRO-BOLD.OTF", "MYRIADPRO-REGULAR.OTF"],
}
CARPETA_INCLUIDA = Path("recursos") / "fuentes"


def faltantes(instaladas):
    return [f for f in FUENTES if f not in instaladas]


def incluidas():
    """True si el programa trae los archivos de fuentes adentro."""
    carpeta = rutas.recurso(CARPETA_INCLUIDA)
    return carpeta.is_dir() and any(carpeta.iterdir())


def _instalar_windows(archivo: Path):
    import ctypes
    import os
    import winreg
    destino_dir = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / archivo.name
    if not destino.exists():
        shutil.copy2(archivo, destino)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows NT\CurrentVersion\Fonts", 0,
                        winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, f"{archivo.stem} (OpenType)", 0, winreg.REG_SZ, str(destino))
    ctypes.windll.gdi32.AddFontResourceW(str(destino))


def _instalar_mac(archivo: Path):
    destino_dir = Path.home() / "Library" / "Fonts"
    destino_dir.mkdir(parents=True, exist_ok=True)
    if not (destino_dir / archivo.name).exists():
        shutil.copy2(archivo, destino_dir / archivo.name)


def _instalar_archivos(archivos):
    hechos = []
    for archivo in archivos:
        if rutas.ES_WINDOWS:
            _instalar_windows(archivo)
        else:
            _instalar_mac(archivo)
        hechos.append(archivo.name)
    if rutas.ES_WINDOWS and hechos:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 2, 1000, None)
    return hechos


def _buscar(carpeta: Path, familias):
    """Archivos de la carpeta (y subcarpetas) que corresponden a las familias pedidas."""
    buscados = {n.lower() for f in familias for n in FUENTES.get(f, [])}
    return [p for p in carpeta.rglob("*") if p.is_file() and p.name.lower() in buscados]


def instalar(familias):
    """Instala las fuentes incluidas en el programa. Devuelve los archivos instalados."""
    carpeta = rutas.recurso(CARPETA_INCLUIDA)
    return _instalar_archivos(_buscar(carpeta, familias)) if carpeta.is_dir() else []


def instalar_desde(carpeta, familias=None):
    """Instala las fuentes que estén en una carpeta elegida por el usuario."""
    return _instalar_archivos(_buscar(Path(carpeta), familias or list(FUENTES)))
