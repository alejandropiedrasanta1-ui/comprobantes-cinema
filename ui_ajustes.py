"""Pantalla «Ajustes»: carpeta de salida, reserva, vista en vivo, PhotoCraft, fuentes y tema."""
import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon as FIF, PushButton, PushSettingCard,
                            SettingCard, SettingCardGroup, SmoothScrollArea, SwitchButton, Theme,
                            TitleLabel, setTheme)

import fuentes
import motor
import rutas
from ui_comun import CTRL, Monto, abrir, aviso

TEMAS = {"Oscuro": Theme.DARK, "Claro": Theme.LIGHT, "Automático (como el sistema)": Theme.AUTO}


def aplicar_tema(nombre):
    setTheme(TEMAS.get(nombre, Theme.DARK))


class _EstadoFuentes(QThread):
    listo = Signal(list)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

    def run(self):
        try:
            motor._cache_fuentes = None
            self.listo.emit(fuentes.faltantes(motor._fuentes_instaladas(self.cfg)))
        except Exception:
            self.listo.emit(["(no se pudo revisar)"])


class AjustesInterface(QWidget):
    photocraft_cambiado = Signal()
    reserva_cambiada = Signal()
    vista_cambiada = Signal(bool)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("ajustes")
        self.cfg = cfg
        self.hilo = None
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        raiz.addWidget(scroll)
        v = QVBoxLayout(cont)
        v.setContentsMargins(36, 28, 36, 28)
        v.setSpacing(18)
        v.addWidget(TitleLabel("Ajustes"))

        # ---------- Comprobantes ----------
        g1 = SettingCardGroup("Comprobantes", cont)
        self.c_carpeta = PushSettingCard("Cambiar", FIF.FOLDER, "Carpeta de los comprobantes",
                                         cfg["carpeta_salida"])
        self.c_carpeta.clicked.connect(self.cambiar_carpeta)
        b_abrir = PushButton("Abrir")
        b_abrir.clicked.connect(self._abrir_carpeta)
        self.c_carpeta.hBoxLayout.insertWidget(self.c_carpeta.hBoxLayout.count() - 2, b_abrir)
        g1.addSettingCard(self.c_carpeta)
        c_reserva = SettingCard(FIF.TAG, "Reserva por defecto", "Monto que se sugiere al crear un comprobante")
        self.reserva = Monto()
        self.reserva.setValue(int(cfg.get("reserva_por_defecto", 600)))
        self.reserva.setFixedWidth(160)
        self.reserva.editingFinished.connect(self.guardar_reserva)
        c_reserva.hBoxLayout.addWidget(self.reserva, 0, Qt.AlignRight)
        c_reserva.hBoxLayout.addSpacing(16)
        g1.addSettingCard(c_reserva)
        c_vivo = SettingCard(FIF.VIEW, "Vista previa en vivo",
                             "Actualiza el comprobante mientras escribes (usa PhotoCraft unos segundos)")
        self.vivo = SwitchButton()
        self.vivo.setOnText("Sí")
        self.vivo.setOffText("No")
        self.vivo.setChecked(bool(cfg.get("vista_en_vivo", True)))
        self.vivo.checkedChanged.connect(lambda si: self.vista_cambiada.emit(si))
        c_vivo.hBoxLayout.addWidget(self.vivo, 0, Qt.AlignRight)
        c_vivo.hBoxLayout.addSpacing(16)
        g1.addSettingCard(c_vivo)
        v.addWidget(g1)

        # ---------- Programa ----------
        g2 = SettingCardGroup("Programa", cont)
        self.c_pc = PushSettingCard("Buscar", FIF.APPLICATION, "PhotoCraft (photocraft-cli)",
                                    cfg.get("photocraft_cli") or "No encontrado")
        self.c_pc.clicked.connect(self.ubicar_photocraft)
        g2.addSettingCard(self.c_pc)
        self.c_fuentes = PushSettingCard("Instalar desde carpeta…", FIF.FONT, "Fuentes del diseño",
                                         "Revisando…")
        self.c_fuentes.clicked.connect(self.instalar_fuentes)
        g2.addSettingCard(self.c_fuentes)
        c_tema = SettingCard(FIF.BRUSH, "Tema", "Apariencia de la ventana")
        self.tema = ComboBox()
        self.tema.addItems(list(TEMAS))
        self.tema.setCurrentText(cfg.get("tema", "Oscuro"))
        self.tema.currentTextChanged.connect(self.cambiar_tema)
        c_tema.hBoxLayout.addWidget(self.tema, 0, Qt.AlignRight)
        c_tema.hBoxLayout.addSpacing(16)
        g2.addSettingCard(c_tema)
        c_datos = PushSettingCard("Abrir", FIF.HISTORY, "Historial de clientes", str(rutas.BASE_DATOS))
        c_datos.clicked.connect(lambda: abrir(rutas.BASE_DATOS.parent))
        g2.addSettingCard(c_datos)
        v.addWidget(g2)

        modo = "Portable (todo se guarda junto al programa)" if rutas.PORTABLE else "Instalado"
        v.addWidget(CaptionLabel(f"Comprobantes Cinema Productions · versión {rutas.VERSION} · {modo}"))
        v.addWidget(CaptionLabel(f"Atajos: {CTRL}N nuevo · {CTRL}Enter generar · {CTRL}V pegar captura · "
                                 f"{CTRL}F buscar cliente"))
        v.addStretch(1)

    def showEvent(self, e):
        super().showEvent(e)
        self.revisar_fuentes()

    # ---------- acciones ----------
    def _abrir_carpeta(self):
        carpeta = Path(self.cfg["carpeta_salida"])
        carpeta.mkdir(parents=True, exist_ok=True)
        abrir(carpeta)

    def cambiar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta para los comprobantes",
                                                   self.cfg["carpeta_salida"])
        if carpeta:
            self.cfg["carpeta_salida"] = carpeta
            motor.guardar_preferencia("carpeta_salida", carpeta)
            self.c_carpeta.setContent(carpeta)

    def guardar_reserva(self):
        self.cfg["reserva_por_defecto"] = self.reserva.value()
        motor.guardar_preferencia("reserva_por_defecto", self.reserva.value())
        self.reserva_cambiada.emit()

    def ubicar_photocraft(self):
        filtro = "photocraft-cli.exe (photocraft-cli.exe)" if rutas.ES_WINDOWS else "Todos (*)"
        ruta, _ = QFileDialog.getOpenFileName(self, "Ubica PhotoCraft (photocraft-cli)", "", filtro)
        if ruta.endswith(".app"):  # en Mac se puede elegir directamente la app
            dentro = sorted(Path(ruta).glob("Contents/*/photocraft-cli"))
            ruta = str(dentro[0]) if dentro else ""
        if not ruta or not os.path.isfile(ruta):
            return
        self.cfg["photocraft_cli"] = ruta
        motor.guardar_preferencia("photocraft_cli", ruta)
        self.c_pc.setContent(ruta)
        aviso(self, "success", "PhotoCraft", "Listo, se usará esta ubicación.")
        self.photocraft_cambiado.emit()

    def revisar_fuentes(self):
        if not os.path.isfile(self.cfg.get("photocraft_cli") or ""):
            self.c_fuentes.setContent("Primero indica dónde está PhotoCraft")
            return
        if self.hilo and self.hilo.isRunning():
            return
        self.hilo = _EstadoFuentes(self.cfg)
        self.hilo.listo.connect(self._mostrar_fuentes)
        self.hilo.start()

    def _mostrar_fuentes(self, faltan):
        if faltan:
            self.c_fuentes.setContent("Faltan: " + ", ".join(faltan) + " — elige la carpeta donde están")
        else:
            self.c_fuentes.setContent("✓ Lemon Milk, GetVoIP Grotesque y Myriad Pro están instaladas")

    def instalar_fuentes(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta con las fuentes (Lemon Milk, GetVoIP, Myriad Pro)")
        if not carpeta:
            return
        hechos = fuentes.instalar_desde(carpeta)
        if hechos:
            aviso(self, "success", "Fuentes instaladas", ", ".join(hechos), 6000)
        else:
            aviso(self, "warning", "No encontré las fuentes",
                  "En esa carpeta no están LEMONMILK-Bold.otf, GetVoIP Grotesque.otf ni MYRIADPRO-*.OTF.", 8000)
        self.revisar_fuentes()

    def cambiar_tema(self, nombre):
        self.cfg["tema"] = nombre
        motor.guardar_preferencia("tema", nombre)
        aplicar_tema(nombre)
