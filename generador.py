"""Comprobantes Cinema Productions — punto de entrada.

  python generador.py                       abre el programa
  python generador.py --autoprueba INFORME  genera un comprobante de cada paquete sin ventana
                                            (sirve para verificar una instalación)
  python generador.py --prueba-vivo CARPETA [--cli PHOTOCRAFT]
                                            prueba la vista en vivo escribiendo como un usuario
                                            y mide cuánto tarda cada cambio en verse
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

    app.configurar_letra()
    # (tema, tamaño): monitor grande, laptop / MacBook Air y la ventana más chica permitida
    tamanos = [("Oscuro", "", (1380, 880)), ("Oscuro", "_laptop", (1180, 700)), ("Oscuro", "_chica", app.MINIMO),
               ("Claro", "", (1380, 880))]
    for tema, sufijo, tam in tamanos:
        aplicar_tema(tema)
        setThemeColor(QColor(app.COLOR_MARCA))
        v = app.Ventana(cfg, revisar=False)
        v.setMicaEffectEnabled(False)   # con Mica (Windows 11) el fondo lo pinta Windows y no sale en la imagen
        v.setMinimumSize(*app.MINIMO)
        v.resize(*tam)
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
        n.extras = [("cabina360", 1)]       # un extra de ejemplo: se ve su ficha y el total con el extra
        n._poner_extras()
        paginas = [("1_nuevo", lambda: n.abrir_bloque(n.b1)), ("2_paquete", lambda: n.abrir_bloque(n.b2)),
                   ("3_clientes", lambda: v.switchTo(v.historial)), ("4_paquetes", lambda: v.switchTo(v.paquetes)),
                   ("5_ajustes", lambda: v.switchTo(v.ajustes))]
        if tema == "Claro":
            paginas = paginas[:1] + paginas[2:3]
        elif sufijo:
            paginas = [paginas[0], ("1b_vista", lambda: n._ver_vista(True)), paginas[2], paginas[3], paginas[4]]
        for nombre, accion in paginas:
            accion()
            if nombre == "3_clientes":
                esperar(400)
                v.historial.tabla.selectRow(1)
            esperar(1200)
            archivo = carpeta / f"{nombre}_{tema.lower()}{sufijo}.png"
            v.grab().save(str(archivo))  # la ventana completa, aunque la pantalla sea más chica
            print("captura:", archivo.name)
        v.close()
        esperar(500)
    return 0


def _prueba_vivo(carpeta, cli=None):
    """Prueba la vista en vivo como un usuario: escribe letra por letra, pone la captura, cambia de
    paquete, usa el zoom y agranda la ventana. Mide cuánto tarda en verse cada cambio, guarda
    capturas de pantalla y un informe (vista_en_vivo.txt). cli: otro photocraft-cli (p. ej. el
    simulado de herramientas/ en la Mac de GitHub, que no tiene PhotoCraft). Devuelve 0 si todo
    se vio a tiempo y sin errores."""
    import statistics
    import tempfile
    import time
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    import app

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas.BASE_DATOS = Path(tempfile.mkdtemp()) / "prueba.db"
    qa = QApplication(sys.argv)
    app.configurar_letra()
    cfg = motor.cargar_config()
    cfg["vista_en_vivo"] = True
    if cli:
        cfg["photocraft_cli"] = str(Path(cli).resolve())
    v = app.Ventana(cfg, revisar=False)
    if hasattr(v, "setMicaEffectEnabled"):
        v.setMicaEffectEnabled(False)
    v.resize(1180, 760)
    v.move(40, 40)
    v.show()
    n = v.nuevo
    t0 = time.perf_counter()
    reloj = lambda: time.perf_counter() - t0
    lineas, errores = [], []

    def anotar(texto):
        lineas.append(texto)
        print(texto, flush=True)

    def esperar(ms):
        lazo = QEventLoop()
        QTimer.singleShot(int(ms), lazo.quit)
        lazo.exec()

    # Cada vista que empieza se anota con los datos que lleva; al verse, cuánto tardó.
    pedidas, vistas = [], []
    orig_render, orig_lista, orig_fallo = n._render_vista, n._vista_lista, n._vista_fallo

    def render():
        antes = n.n_vista
        orig_render()
        if n.n_vista != antes:
            pedidas.append((reloj(), n.festejado.text(), n.lugar.text(), n.paquete, n.zona.ruta, n.zoom))

    def lista(ruta):
        inicio, *datos = pedidas.pop(0)
        vistas.append((reloj(), reloj() - inicio, *datos))
        orig_lista(ruta)

    def fallo(msg):
        pedidas.pop(0)
        errores.append(msg)
        anotar(f"  ERROR en la vista: {msg.splitlines()[0]}")
        orig_fallo(msg)

    n._render_vista, n._vista_lista, n._vista_fallo = render, lista, fallo
    n.temporizador.timeout.disconnect()
    n.temporizador.timeout.connect(n._render_vista)
    n.tope_vista.timeout.disconnect()
    n.tope_vista.timeout.connect(n._render_vista)

    def hasta_ver(condicion, limite=60):
        """Espera a que se vea una vista que cumpla la condición; devuelve el momento o None."""
        fin = time.perf_counter() + limite
        while time.perf_counter() < fin:
            for vista in vistas:
                if condicion(vista):
                    return vista[0]
            esperar(15)
        return None

    def foto(nombre):
        v.grab().save(str(carpeta / f"vivo_{nombre}.png"))

    def escribir(campo, texto, pausa_ms):
        campo.setFocus()
        campo.clear()
        esperar(400)
        del vistas[:]
        inicio = reloj()
        for letra in texto:
            campo.end(False)
            campo.insert(letra)
            ultima = reloj()   # la hora de la tecla, no la de después de la pausa
            esperar(pausa_ms)
        visto = hasta_ver(lambda vi: vi[2:6] == (n.festejado.text(), n.lugar.text(), n.paquete, n.zona.ruta))
        durante = sum(1 for vi in vistas if vi[0] <= ultima)
        tiempos = [vi[1] for vi in vistas]
        if visto is None:
            errores.append(f"no se vio «{texto}»")
            anotar(f"  NO SE VIO el texto final «{texto}»")
        else:
            anotar(f"  {len(texto)} letras en {ultima - inicio:.1f} s · vistas mientras escribía: {durante} · "
                   f"texto final visible {1000 * (visto - ultima):.0f} ms después de la última tecla · "
                   f"cada vista: mediana {1000 * statistics.median(tiempos):.0f} ms, máx {1000 * max(tiempos):.0f} ms")

    def paso(nombre, accion, condicion):
        del vistas[:]
        inicio = reloj()
        accion()
        visto = hasta_ver(condicion)
        if visto is None:
            errores.append(f"{nombre}: no se vio")
            anotar(f"{nombre}: NO SE VIO")
        else:
            anotar(f"{nombre}: visible en {1000 * (visto - inicio):.0f} ms")

    anotar(f"Vista en vivo · {sys.platform} · PhotoCraft: {cfg.get('photocraft_cli')}")
    visto = hasta_ver(lambda vi: True, 120)
    anotar(f"Primera vista al abrir: {visto:.1f} s" if visto else "Primera vista al abrir: NO SE VIO")
    if not visto:
        errores.append("primera vista")
    foto("0_inicio")
    anotar("Nombre, escribiendo normal (8 letras/s):")
    escribir(n.festejado, "Marta Alejandra y José Pérez", 125)
    anotar("Lugar, escribiendo rápido (20 letras/s):")
    escribir(n.lugar, "Hotel Casa Santo Domingo, Antigua", 50)
    foto("1_textos")
    imagen = Path(tempfile.gettempdir()) / "prueba_vivo_captura.png"
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (900, 1600), (40, 120, 200))
    ImageDraw.Draw(im).text((60, 700), "CAPTURA DE PRUEBA", fill="white")
    im.save(imagen)
    paso("Poner la captura del pago", lambda: n.zona.usar(str(imagen)), lambda vi: vi[5] == str(imagen))
    foto("2_captura")
    otro = [p for p in cfg["paquetes"] if p != n.paquete][-1]
    paso(f"Cambiar al paquete {otro}", lambda: n.elegir_paquete(otro), lambda vi: vi[4] == otro)
    anotar("Nombre en el paquete nuevo:")
    escribir(n.festejado, "Daniel y Sofía", 125)
    foto("3_paquete")
    paso("Zoom (vista más grande y nítida)", n._alternar_zoom, lambda vi: vi[6] is True)
    foto("4_zoom")
    n._alternar_zoom()
    esperar(800)
    v.resize(1380, 880)
    esperar(300)
    if n.pix and max(n.pix.width(), n.pix.height()) + 48 < n._lado_vista():
        paso("Agrandar la ventana (vista más nítida)", lambda: None, lambda vi: True)
    esperar(500)
    foto("5_ventana_grande")
    if n.vista_ruta:
        import shutil
        shutil.copy(n.vista_ruta, carpeta / f"vivo_ultima_vista{Path(n.vista_ruta).suffix}")
    anotar(f"Fallos de la vía rápida: {motor._fallos_sesion} · errores: {len(errores)}")
    anotar("RESULTADO: " + ("OK" if not errores and motor._fallos_sesion == 0 else "FALLÓ · " + " · ".join(errores)))
    (carpeta / "vista_en_vivo.txt").write_text("\n".join(lineas), encoding="utf-8")
    while n.vista_trabajo and n.vista_trabajo.isRunning():
        esperar(50)
    v.close()
    motor._sesion.cerrar()
    return 0 if not errores and motor._fallos_sesion == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--verificar":
        sys.exit(_verificar())
    if len(sys.argv) in (3, 5) and sys.argv[1] == "--prueba-vivo":
        sys.exit(_prueba_vivo(sys.argv[2], sys.argv[4] if len(sys.argv) == 5 and sys.argv[3] == "--cli" else None))
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
