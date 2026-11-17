"""Comprobantes Cinema Productions — punto de entrada.

  python generador.py                       abre el programa
  python generador.py --autoprueba INFORME  genera un comprobante de cada paquete sin ventana
                                            (sirve para verificar una instalación)
"""
import sys
import traceback
from datetime import date
from pathlib import Path

import motor
import rutas


def _autoprueba(reporte):
    lineas = []
    try:
        cfg = motor.cargar_config()
        cfg["carpeta_salida"] = str(Path(reporte).parent / "autoprueba")
        for clave in cfg["paquetes"]:
            r = motor.generar(dict(evento="Boda", paquete=clave, festejado="Prueba", lugar="Guatemala",
                                   fecha_evento=date.today(), fecha_comprobante=date.today(),
                                   contacto="+502 0000 0000", total=cfg["paquetes"][clave]["precio"],
                                   monto=600, captura=str(rutas.recurso("recursos/icono.png"))), cfg)
            lineas.append(f"OK {clave} {r}")
    except Exception:
        lineas.append("ERROR " + traceback.format_exc())
    Path(reporte).write_text("\n".join(lineas), encoding="utf-8")
    return 0 if lineas and all(l.startswith("OK") for l in lineas) else 1


def _verificar():
    """Arma la ventana completa sin mostrarla (sirve en una Mac sin PhotoCraft, p. ej. GitHub Actions)."""
    import os
    if sys.platform != "darwin":
        # En Mac no: la ventana sin bordes usa la vista nativa de Cocoa y se cae en modo offscreen
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import app
    qa = QApplication(sys.argv)
    ventana = app.Ventana(motor.cargar_config())
    print("OK interfaz:", [ventana.stackedWidget.widget(i).objectName() for i in range(ventana.stackedWidget.count())])
    ventana.close()
    qa.quit()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--verificar":
        sys.exit(_verificar())
    if len(sys.argv) == 3 and sys.argv[1] == "--autoprueba":
        try:
            import pyi_splash
            pyi_splash.close()
        except ImportError:
            pass
        sys.exit(_autoprueba(sys.argv[2]))
    import app
    sys.exit(app.main())
