"""Ventana principal (estilo Fluent de Windows 11) con menú lateral."""
import os
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTimer, QTranslator
from PySide6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QLineEdit
from qfluentwidgets import (FluentIcon as FIF, FluentTranslator, FluentWindow, MessageBox,
                            NavigationAvatarWidget, NavigationItemPosition, setThemeColor)

import motor
import rutas
from ui_ajustes import AjustesInterface, aplicar_tema
from ui_comun import Revision, aviso
from ui_historial import HistorialInterface
from ui_nuevo import NuevoInterface
from ui_paquetes import PaquetesInterface

COLOR_MARCA = "#e0262b"


class Ventana(FluentWindow):
    def __init__(self, cfg, revisar=True):
        super().__init__()
        self.cfg = cfg
        self.revision = None
        self.setWindowTitle("Comprobantes · Cinema Productions")
        self.setWindowIcon(QIcon(str(rutas.recurso("recursos/icono.png"))))
        self.resize(1380, 900)
        self.setMinimumSize(1140, 720)

        self.nuevo = NuevoInterface(cfg, self)
        self.historial = HistorialInterface(cfg, self)
        self.paquetes = PaquetesInterface(cfg, self)
        self.ajustes = AjustesInterface(cfg, self)
        self.addSubInterface(self.nuevo, FIF.ADD, "Nuevo comprobante")
        self.addSubInterface(self.historial, FIF.PEOPLE, "Clientes y pagos")
        self.addSubInterface(self.paquetes, FIF.SHOPPING_CART, "Paquetes")
        self.navigationInterface.addWidget(
            routeKey="marca",
            widget=NavigationAvatarWidget("Cinema Productions", str(rutas.recurso("recursos/icono.png"))),
            onClick=lambda: self.switchTo(self.ajustes),
            position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.ajustes, FIF.SETTING, "Ajustes", NavigationItemPosition.BOTTOM)

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

        pantalla = QApplication.primaryScreen().availableGeometry()
        self.move(pantalla.center() - self.rect().center())
        if revisar:
            QTimer.singleShot(600, self.revisar_entorno)

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


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    # Español: calendario, botones y textos de Fluent-Widgets y de Qt
    QLocale.setDefault(QLocale(QLocale.Spanish, QLocale.Guatemala))
    traductores = [FluentTranslator(QLocale(QLocale.Spanish, QLocale.Spain)), QTranslator()]
    traductores[1].load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath))
    for tr in traductores:
        app.installTranslator(tr)
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
