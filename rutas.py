"""Ubicaciones del programa: recursos incluidos (solo lectura), datos del usuario y salida.

Modo portable (un solo .exe): los ajustes y los comprobantes se guardan junto al .exe,
sin escribir nada en la carpeta del usuario."""
import os
import sys
from pathlib import Path

APP = "Comprobantes Cinema Productions"
VERSION = "2.2.2"
ES_WINDOWS = sys.platform.startswith("win")
ES_MAC = sys.platform == "darwin"
CONGELADO = getattr(sys, "frozen", False)

# Recursos incluidos: junto al código o, en el programa compilado, dentro del paquete.
RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CARPETA_APP = Path(sys.executable).resolve().parent if CONGELADO else Path(__file__).resolve().parent


def _escribible(carpeta: Path):
    try:
        prueba = carpeta / ".prueba_escritura"
        prueba.write_text("ok")
        prueba.unlink()
        return True
    except OSError:
        return False


PORTABLE = CONGELADO and (RECURSOS / "portable.flag").exists() and _escribible(CARPETA_APP)

if PORTABLE:
    CONFIG_USUARIO = CARPETA_APP / "Comprobantes Cinema - ajustes.json"
    BASE_DATOS = CARPETA_APP / "Comprobantes Cinema - historial.db"
    SALIDA_POR_DEFECTO = CARPETA_APP / "COMPROBANTES GENERADOS"
else:
    if ES_WINDOWS:
        _datos = Path(os.environ.get("APPDATA", Path.home())) / APP
    elif ES_MAC:
        _datos = Path.home() / "Library" / "Application Support" / APP
    else:
        _datos = Path.home() / ".config" / APP
    CONFIG_USUARIO = _datos / "config.json"
    BASE_DATOS = _datos / "historial.db"
    SALIDA_POR_DEFECTO = Path.home() / "Documents" / APP


def recurso(relativa):
    """Resuelve una ruta de config: relativa -> dentro de los recursos; absoluta -> tal cual."""
    p = Path(relativa)
    return p if p.is_absolute() else RECURSOS / p
