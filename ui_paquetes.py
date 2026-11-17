"""Pantalla «Paquetes»: lo que incluye cada paquete y sus precios (editables)."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, FluentIcon as FIF, PrimaryPushButton,
                            SimpleCardWidget, SmoothScrollArea, StrongBodyLabel, SubtitleLabel,
                            TitleLabel)

import motor
from ui_comun import COLOR_PAQUETE, NOMBRES_PAQUETE, Monto, Rejilla, aviso, q


class _Tarjeta(SimpleCardWidget):
    """Tarjeta del paquete con la franja de su color."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = QColor(color)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawRoundedRect(QRectF(0, 14, 4, self.height() - 28), 2, 2)
        p.end()


class PaquetesInterface(QWidget):
    precios_cambiados = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("paquetes")
        self.cfg = cfg
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        raiz.addWidget(scroll)
        v = QVBoxLayout(cont)
        v.setContentsMargins(36, 28, 36, 28)
        v.setSpacing(14)

        cab = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(2)
        tit.addWidget(TitleLabel("Paquetes"))
        tit.addWidget(CaptionLabel("Lo que incluye cada paquete. Puedes cambiar los precios aquí."))
        cab.addLayout(tit)
        cab.addStretch(1)
        guardar = PrimaryPushButton(FIF.SAVE, "Guardar precios")
        guardar.clicked.connect(self.guardar)
        cab.addWidget(guardar, 0, Qt.AlignVCenter)
        v.addLayout(cab)

        tarjetas = []
        self.precios = {}
        destacado = cfg.get("paquete_destacado", "COMPLETO")
        reserva = cfg.get("reserva_por_defecto", 600)
        for clave, paq in cfg["paquetes"].items():
            card = _Tarjeta(COLOR_PAQUETE.get(clave, "#888888"))
            c = QVBoxLayout(card)
            c.setContentsMargins(24, 18, 20, 18)
            c.setSpacing(6)
            fila = QHBoxLayout()
            nombre = QVBoxLayout()
            nombre.setSpacing(0)
            titulo = QHBoxLayout()
            titulo.setSpacing(8)
            titulo.addWidget(SubtitleLabel(NOMBRES_PAQUETE.get(clave, clave.title())))
            if clave == destacado:
                sello = QLabel("MÁS VENDIDO")
                sello.setStyleSheet("background:#e0262b;color:white;border-radius:8px;padding:1px 7px;"
                                    "font-size:9px;font-weight:700;")
                titulo.addWidget(sello, 0, Qt.AlignVCenter)
            titulo.addStretch(1)
            nombre.addLayout(titulo)
            nombre.addWidget(CaptionLabel(f"{len(paq.get('incluye', []))} servicios · reserva sugerida {q(reserva)}"))
            fila.addLayout(nombre, 1)
            precio = Monto()
            precio.setValue(int(paq["precio"]))
            precio.setFixedWidth(160)
            self.precios[clave] = precio
            fila.addWidget(precio, 0, Qt.AlignTop)
            c.addLayout(fila)
            c.addSpacing(4)
            for titulo_s, detalle, _ in paq.get("incluye", []):
                fila_s = QHBoxLayout()
                fila_s.setSpacing(8)
                punto = QLabel("●")
                punto.setStyleSheet(f"color:{COLOR_PAQUETE.get(clave, '#888')};font-size:9px;")
                fila_s.addWidget(punto, 0, Qt.AlignVCenter)
                fila_s.addWidget(StrongBodyLabel(titulo_s))
                if detalle:
                    det = CaptionLabel(detalle.strip("()"))
                    det.setWordWrap(True)
                    fila_s.addWidget(det, 1, Qt.AlignVCenter)
                fila_s.addStretch(1)
                c.addLayout(fila_s)
            c.addStretch(1)
            tarjetas.append(card)
        v.addWidget(Rejilla(tarjetas, max_columnas=2, ancho_min=380, espacio=14))
        nota = CaptionLabel("Para cambiar los servicios de un paquete se edita la plantilla PSD "
                            "(PROGRAMA\\config_default.json + crear_plantillas.py) y se vuelve a crear el programa.")
        nota.setWordWrap(True)
        v.addWidget(nota)
        v.addStretch(1)

    def guardar(self):
        nuevos = {clave: {"precio": sp.value()} for clave, sp in self.precios.items()}
        for clave, datos in nuevos.items():
            self.cfg["paquetes"][clave]["precio"] = datos["precio"]
        motor.guardar_preferencia("paquetes", nuevos)
        self.precios_cambiados.emit()
        aviso(self, "success", "Precios guardados", "Los nuevos comprobantes usarán estos precios.")
