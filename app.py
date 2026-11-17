"""Ventana principal: barra lateral con ícono y nombre de cada pantalla (logo arriba, Ajustes abajo)."""
import os
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QRectF, Qt, QTimer, QTranslator
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QLineEdit
from qfluentwidgets import (FluentIcon as FIF, FluentTranslator, MSFluentWindow, MessageBox,
                            NavigationItemPosition, NavigationWidget, setFontFamilies, setThemeColor)

import estilo
import motor
import rutas
from ui_ajustes import AjustesInterface, aplicar_tema
from ui_comun import Revision, aviso
from ui_historial import HistorialInterface
from ui_nuevo import NuevoInterface
from ui_paquetes import PaquetesInterface

COLOR_MARCA = "#e0262b"
ES_MAC = sys.platform == "darwin"
IDEAL = (1380, 900)      # tamaño cómodo en monitores grandes
MINIMO = (760, 540)      # cabe en pantallas chicas: todo se reacomoda (ver Rejilla y los modos compactos)
MARGEN_MAC = 84          # ancho de los botones rojo/amarillo/verde de macOS


class _Marca(NavigationWidget):
    """Logo de la app arriba de la barra lateral, con un brillo rojo suave."""

    def __init__(self, parent=None):
        super().__init__(isSelectable=False, parent=parent)
        self.pm = QPixmap(str(rutas.recurso("recursos/icono.png")))
        self.setFixedSize(64, 62)
        self.setToolTip("Comprobantes · Cinema Productions")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        lado = 38
        r = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        p.setPen(Qt.NoPen)
        for i, a in enumerate((26, 14, 7)):
            p.setBrush(estilo.alfa(estilo.ROJO, a))
            g = 3 + 4 * i
            p.drawRoundedRect(r.adjusted(-g, -g, g, g), 12 + g, 12 + g)
        dpr = self.devicePixelRatioF()
        pm = self.pm.scaled(int(lado * dpr), int(lado * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        p.drawPixmap(r.topLeft(), pm)
        p.end()


class Ventana(MSFluentWindow):
    def __init__(self, cfg, revisar=True):
        super().__init__()
        self.cfg = cfg
        self.revision = None
        self.setWindowTitle("Comprobantes · Cinema Productions")
        self.setWindowIcon(QIcon(str(rutas.recurso("recursos/icono.png"))))
        # Fondo grafito parejo (sin Mica: en Windows 11 teñía la ventana con el fondo de pantalla)
        self.setMicaEffectEnabled(False)
        self.setCustomBackgroundColor(QColor("#F5F5F7"), QColor("#0F0F12"))
        self.navigationInterface.setSelectedColor(QColor(estilo.ROJO), QColor(estilo.ROJO_CLARO))

        self.nuevo = NuevoInterface(cfg, self)
        self.historial = HistorialInterface(cfg, self)
        self.paquetes = PaquetesInterface(cfg, self)
        self.ajustes = AjustesInterface(cfg, self)
        self.navigationInterface.addWidget("marca", _Marca(), lambda: self.switchTo(self.nuevo))
        self.addSubInterface(self.nuevo, FIF.ADD, "Nuevo")
        self.addSubInterface(self.historial, FIF.PEOPLE, "Clientes")
        self.addSubInterface(self.paquetes, FIF.SHOPPING_CART, "Paquetes")
        self.addSubInterface(self.ajustes, FIF.SETTING, "Ajustes", position=NavigationItemPosition.BOTTOM)

        self.nuevo.registrado.connect(self.historial.refrescar)
        self.historial.pedir_nuevo.connect(lambda: self.switchTo(self.nuevo))
        self.paquetes.precios_cambiados.connect(self.nuevo.actualizar_precios)
        self.ajustes.photocraft_cambiado.connect(self.revisar_entorno)
        self.ajustes.vista_cambiada.connect(self.nuevo.poner_en_vivo)
        self.nuevo.en_vivo.checkedChanged.connect(
            lambda si: self.ajustes.vivo.isChecked() != si and self.ajustes.vivo.setChecked(si))
        QShortcut(QKeySequence.Paste, self, activated=self._pegar)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._nuevo)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._buscar)
        for tecla in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(tecla), self, activated=self._generar)

        self.ajustar_a_pantalla()
        if revisar:
            QTimer.singleShot(600, self.revisar_entorno)

    def ajustar_a_pantalla(self):
        """Tamaño según la pantalla (sin la barra de menú ni el Dock / la barra de tareas): cabe completa en una
        MacBook, una laptop o un monitor grande, y queda centrada."""
        zona = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.setMinimumSize(min(MINIMO[0], zona.width()), min(MINIMO[1], zona.height()))
        ancho = max(self.minimumWidth(), min(IDEAL[0], int(zona.width() * 0.94)))
        alto = max(self.minimumHeight(), min(IDEAL[1], int(zona.height() * 0.94)))
        self.resize(ancho, alto)
        self.move(zona.x() + (zona.width() - ancho) // 2, zona.y() + (zona.height() - alto) // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if ES_MAC:   # el título va después de los botones de macOS, no encima
            self.titleBar.move(MARGEN_MAC, 0)
            self.titleBar.resize(self.width() - MARGEN_MAC, self.titleBar.height())

    def showEvent(self, e):
        super().showEvent(e)
        if ES_MAC:   # a veces macOS los esconde al mostrar la ventana: se vuelven a poner
            QTimer.singleShot(150, lambda: self.setSystemTitleBarButtonVisible(True))

    def _nuevo(self):
        self.switchTo(self.nuevo)
        self.nuevo.limpiar()

    def _buscar(self):
        self.switchTo(self.historial)
        self.historial.buscar.setFocus()
        self.historial.buscar.selectAll()

    def _generar(self):
        actual = self.stackedWidget.currentWidget()
        if actual is self.historial and self.historial.actual:
            self.historial.generar_abono()
        elif actual is self.nuevo:
            self.nuevo.generar()

    def _pegar(self):
        foco = QApplication.focusWidget()
        if isinstance(foco, QLineEdit):
            foco.paste()
        elif self.stackedWidget.currentWidget() is self.historial and self.historial.actual:
            self.historial.zona.pegar()
        else:
            self.switchTo(self.nuevo)
            self.nuevo.pegar()

    def revisar_entorno(self):
        if not os.path.isfile(self.cfg.get("photocraft_cli") or ""):
            caja = MessageBox("Falta PhotoCraft",
                              "Este programa usa PhotoCraft para crear los comprobantes y no lo encontré.\n\n"
                              "Si ya está instalado, indica dónde está.", self)
            caja.yesButton.setText("Buscar PhotoCraft")
            caja.cancelButton.setText("Más tarde")
            if caja.exec():
                self.switchTo(self.ajustes)
                self.ajustes.ubicar_photocraft()
            return
        self.revision = Revision(self.cfg)
        self.revision.listo.connect(lambda m: aviso(self.nuevo, "info", "Fuentes", m, 6000))
        self.revision.start()


def configurar_letra():
    if ES_MAC:
        # en Mac no existe Segoe UI (la de Windows): se usa la letra del sistema, igual que las apps de Apple
        setFontFamilies([".AppleSystemUIFont", "Helvetica Neue", "PingFang SC"])


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    # Español: calendario, botones y textos de Fluent-Widgets y de Qt
    QLocale.setDefault(QLocale(QLocale.Spanish, QLocale.Guatemala))
    traductores = [FluentTranslator(QLocale(QLocale.Spanish, QLocale.Spain)), QTranslator()]
    traductores[1].load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath))
    for tr in traductores:
        app.installTranslator(tr)
    configurar_letra()
    cfg = motor.cargar_config()
    aplicar_tema(cfg.get("tema", "Oscuro"))
    setThemeColor(QColor(COLOR_MARCA))
    ventana = Ventana(cfg)
    ventana.show()
    try:  # cierra la pantalla de carga de la versión portable
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass
    return app.exec()
