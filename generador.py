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


def _capturas(carpeta):
    """Abre la ventana con datos de ejemplo inventados y guarda una imagen de cada pantalla."""
    import tempfile
    from PySide6.QtCore import QDate, QEventLoop, QLocale, QTimer, QTranslator, QLibraryInfo
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import FluentTranslator, setThemeColor
    import app
    import registro
    from ui_ajustes import aplicar_tema

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas.BASE_DATOS = Path(tempfile.mkdtemp()) / "ejemplo.db"
    hoy = date.today()
    ejemplos = [("María y José", "Boda", "COMPLETO", "Hotel Casa Santo Domingo", 70, 3500, [600]),
                ("Valeria López", "XV años", "INTERMEDIO", "Salón Los Arcos", 25, 2200, [600, 800]),
                ("Daniel y Sofía", "Boda", "PREMIUM", "Finca El Zapote", 45, 5200, [600, 4600]),
                ("Ana y Carlos", "Boda", "ESENCIAL", "Antigua Guatemala", 110, 1500, [600])]
    from datetime import timedelta
    for nombre, evento, paquete, lugar, dias, total, pagos in ejemplos:
        cid = registro.nuevo_cliente(nombre, "+502 5555 0000", evento, paquete, lugar, hoy + timedelta(days=dias), total)
        for i, monto in enumerate(pagos):
            registro.agregar_pago(cid, hoy, monto, "Reserva" if i == 0 else "Abono", "")

    qa = QApplication(sys.argv)
    QLocale.setDefault(QLocale(QLocale.Spanish, QLocale.Guatemala))
    trad = [FluentTranslator(QLocale(QLocale.Spanish, QLocale.Spain)), QTranslator()]
    trad[1].load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath))
    for t in trad:
        qa.installTranslator(t)
    cfg = motor.cargar_config()
    cfg["vista_en_vivo"] = False   # en la Mac de prueba no hay PhotoCraft: se ve la plantilla

    def esperar(ms):
        lazo = QEventLoop()
        QTimer.singleShot(ms, lazo.quit)
        lazo.exec()

    for tema in ("Oscuro", "Claro"):
        aplicar_tema(tema)
        setThemeColor(QColor(app.COLOR_MARCA))
        v = app.Ventana(cfg, revisar=False)
        v.resize(1380, 880)
        v.move(60, 60)
        v.show()
        v.raise_()
        v.activateWindow()
        esperar(1500)
        n = v.nuevo
        n.festejado.setText("María y José")
        n.lugar.setText("Hotel Casa Santo Domingo, Antigua")
        n.telefono.setText("+502 5555 0000")
        n.fecha_evento.setDate(QDate.currentDate().addDays(70))
        n.elegir_paquete("COMPLETO")
        paginas = [("1_nuevo", lambda: n.abrir_bloque(n.b1)), ("2_paquete", lambda: n.abrir_bloque(n.b2)),
                   ("3_clientes", lambda: v.switchTo(v.historial)), ("4_paquetes", lambda: v.switchTo(v.paquetes)),
                   ("5_ajustes", lambda: v.switchTo(v.ajustes))]
        if tema == "Claro":
            paginas = paginas[:1] + paginas[2:3]
        for nombre, accion in paginas:
            accion()
            if nombre == "3_clientes":
                esperar(400)
                v.historial.tabla.selectRow(1)
            esperar(1200)
            archivo = carpeta / f"{nombre}_{tema.lower()}.png"
            v.grab().save(str(archivo))  # la ventana completa, aunque la pantalla sea más chica
            print("captura:", archivo.name)
        v.close()
        esperar(500)
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--verificar":
        sys.exit(_verificar())
    if len(sys.argv) == 3 and sys.argv[1] == "--capturas":
        sys.exit(_capturas(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--autoprueba":
        try:
            import pyi_splash
            pyi_splash.close()
        except ImportError:
            pass
        sys.exit(_autoprueba(sys.argv[2]))
    import app
    sys.exit(app.main())
