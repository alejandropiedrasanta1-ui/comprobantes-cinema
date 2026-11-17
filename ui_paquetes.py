"""Pantalla «Paquetes»: lo que incluye cada paquete y sus precios (editables)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, FluentIcon as FIF, PrimaryPushButton, PushButton,
                            SmoothScrollArea, StrongBodyLabel, SubtitleLabel, TitleLabel, ToolTipFilter)

import estilo
import motor
import rutas
from estilo import Icono, Pildora, Separador, Tarjeta
from ui_comun import (COLOR_PAQUETE, ICONO_PAQUETE, NOMBRES_PAQUETE, Monto, Rejilla, abrir, aviso, q,
                      servicio_legible)


def _servicio(titulo, detalle, icono_s, color):
    """Fila «✓ [ícono] Título · detalle» de la lista de servicios (con el texto legible para la pantalla)."""
    titulo, detalle = servicio_legible(titulo, detalle)
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 2, 0, 2)
    h.setSpacing(10)
    check = QLabel("✓")
    check.setStyleSheet(f"color:{estilo.VERDE};font-weight:700;font-size:13px;background:transparent;")
    check.setFixedWidth(12)
    h.addWidget(check, 0, Qt.AlignTop)
    h.addWidget(Icono(icono_s, 16), 0, Qt.AlignTop)
    v = QVBoxLayout()
    v.setSpacing(0)
    t = StrongBodyLabel(titulo)
    f = t.font()
    f.setPixelSize(13)
    t.setFont(f)
    t.setWordWrap(True)
    v.addWidget(t)
    if detalle:
        d = CaptionLabel(detalle)
        d.setWordWrap(True)
        v.addWidget(d)
    h.addLayout(v, 1)
    return w


class PaquetesInterface(QWidget):
    precios_cambiados = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("paquetes")
        self.cfg = cfg
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        # la cabecera queda fija arriba: «Guardar cambios» siempre a la vista aunque se desplace la lista
        cabecera = QWidget()
        cab = QHBoxLayout(cabecera)
        cab.setContentsMargins(32, 24, 32, 14)
        raiz.addWidget(cabecera)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        raiz.addWidget(scroll, 1)
        v = self.v = QVBoxLayout(cont)
        v.setContentsMargins(32, 4, 32, 28)
        v.setSpacing(18)

        tit = QVBoxLayout()
        tit.setSpacing(2)
        tit.addWidget(TitleLabel("Paquetes"))
        sub = CaptionLabel("Lo que incluye cada paquete. Cambia los precios aquí.")
        sub.setWordWrap(True)
        tit.addWidget(sub)
        cab.addLayout(tit, 1)
        self.nota_cambios = CaptionLabel("")
        cab.addWidget(self.nota_cambios, 0, Qt.AlignVCenter)
        cab.addSpacing(8)
        self.b_guardar = PrimaryPushButton(FIF.SAVE, "Guardar cambios")
        self.b_guardar.setFixedHeight(38)
        estilo.boton_principal(self.b_guardar, FIF.SAVE)
        self.b_guardar.clicked.connect(self.guardar)
        cab.addWidget(self.b_guardar, 0, Qt.AlignVCenter)

        tarjetas = []
        self.precios = {}
        destacado = cfg.get("paquete_destacado", "COMPLETO")
        reserva = cfg.get("reserva_por_defecto", 600)
        for clave, paq in cfg["paquetes"].items():
            color = COLOR_PAQUETE.get(clave, "#888888")
            card = Tarjeta(acento=color)
            card.resaltada = clave == destacado
            card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # las 4 columnas, del mismo ancho
            c = QVBoxLayout(card)
            c.setContentsMargins(20, 22, 20, 18)
            c.setSpacing(10)
            fila = QHBoxLayout()
            fila.setSpacing(12)
            fila.addWidget(Icono(ICONO_PAQUETE.get(clave, "camara"), 22, color=color, fondo=color, caja=42))
            fila.addWidget(SubtitleLabel(NOMBRES_PAQUETE.get(clave, clave.title())), 1)
            c.addLayout(fila)
            precio = Monto()
            precio.setValue(int(paq["precio"]))
            precio.setMinimumWidth(150)
            precio.valueChanged.connect(self._contar_cambios)
            self.precios[clave] = precio
            c.addWidget(precio)
            fila_r = QHBoxLayout()
            fila_r.setSpacing(6)
            fila_r.addWidget(Icono("recibo", 14))
            fila_r.addWidget(CaptionLabel(f"Reserva sugerida {q(reserva)}"))
            fila_r.addStretch(1)
            if clave == destacado:          # aquí sobra lugar: así el nombre del paquete nunca se corta
                fila_r.addWidget(Pildora("Más vendido", estilo.ROJO, solida=True, tam_letra=10, alto=22), 0,
                                 Qt.AlignVCenter)
            c.addLayout(fila_r)
            c.addWidget(Separador())
            incluye = paq.get("incluye", [])
            c.addWidget(StrongBodyLabel(f"Incluye ({len(incluye)} servicios)"))
            for titulo_s, detalle, icono_s in incluye:
                c.addWidget(_servicio(titulo_s, detalle, icono_s, color))
            c.addStretch(1)
            vista = rutas.recurso(f"PLANTILLAS/VISTA PREVIA - {clave}.jpg")
            b_ver = PushButton("Ver plantilla")
            pm = QPixmap(str(vista))
            if not pm.isNull():
                b_ver.setIcon(QIcon(pm.scaledToHeight(64, Qt.SmoothTransformation)))
            b_ver.setToolTip("Abrir la plantilla de este paquete")
            b_ver.installEventFilter(ToolTipFilter(b_ver))
            b_ver.clicked.connect(lambda _=False, r=vista: abrir(r))
            c.addWidget(b_ver)
            tarjetas.append(card)
        v.addWidget(Rejilla(tarjetas, max_columnas=4, ancho_min=236, espacio=16, validas=(1, 2, 4),
                            misma_altura=True))

        nota = Tarjeta(nivel=2, radio=12)
        hn = QHBoxLayout(nota)
        hn.setContentsMargins(16, 12, 16, 12)
        hn.setSpacing(12)
        hn.addWidget(Icono("ajustes", 18))
        texto = CaptionLabel("Los precios los cambias aquí y se usan desde el próximo comprobante. Los servicios de cada "
                             "paquete vienen en el diseño del comprobante: para cambiarlos hace falta actualizar el diseño "
                             "y el programa.")
        texto.setWordWrap(True)
        hn.addWidget(texto, 1)
        v.addWidget(nota)
        v.addStretch(1)
        self._contar_cambios()

    def _contar_cambios(self, *_):
        n = sum(sp.value() != int(self.cfg["paquetes"][clave]["precio"]) for clave, sp in self.precios.items())
        self.nota_cambios.setText(f"{n} cambio{'s' if n != 1 else ''} sin guardar" if n else "")
        self.b_guardar.setEnabled(bool(n))

    def guardar(self):
        nuevos = {clave: {"precio": sp.value()} for clave, sp in self.precios.items()}
        for clave, datos in nuevos.items():
            self.cfg["paquetes"][clave]["precio"] = datos["precio"]
        motor.guardar_preferencia("paquetes", nuevos)
        self._contar_cambios()
        self.precios_cambiados.emit()
        aviso(self, "success", "Precios guardados", "Los nuevos comprobantes usarán estos precios.")
