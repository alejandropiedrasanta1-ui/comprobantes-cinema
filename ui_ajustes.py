"""Pantalla «Ajustes»: menú de secciones a la izquierda y tarjetas agrupadas a la derecha
(comprobantes, vista previa, apariencia, datos y copias)."""
import shutil
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, FluentIcon as FIF, PushButton, Slider, SmoothScrollArea,
                            StrongBodyLabel, SwitchButton, Theme, TitleLabel, setTheme)

import estilo
import motor
import rutas
from estilo import Icono, Separador, Tarjeta
from ui_comun import CTRL, Monto, abrir, aviso

TEMAS = {"Oscuro": Theme.DARK, "Claro": Theme.LIGHT, "Automático (como el sistema)": Theme.AUTO}
SECCIONES = [("comprobantes", "Comprobantes", "recibo"), ("vista", "Movimiento", "chispa"),
             ("apariencia", "Apariencia", "ajustes"), ("datos", "Datos y copias", "carpeta")]


def aplicar_tema(nombre):
    setTheme(TEMAS.get(nombre, Theme.DARK))


class _ItemMenu(QWidget):
    """Renglón del menú de secciones: ícono y nombre; el activo con fondo rojo suave y franja."""
    clicked = Signal()

    def __init__(self, texto, icono_nombre, parent=None):
        super().__init__(parent)
        self.texto, self.icono_nombre, self.activo, self._encima = texto, icono_nombre, False, False
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)

    def poner(self, activo):
        self.activo = activo
        self.update()

    def enterEvent(self, e):
        self._encima = True
        self.update()

    def leaveEvent(self, e):
        self._encima = False
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        if self.activo or self._encima:
            p.setPen(Qt.NoPen)
            p.setBrush(estilo.alfa(estilo.ROJO, 34) if self.activo else estilo.c("sup2"))
            p.drawRoundedRect(r, 9, 9)
        if self.activo:
            p.setBrush(QColor(estilo.ROJO))
            p.drawRoundedRect(QRectF(r.left(), r.top() + 10, 3, r.height() - 20), 1.5, 1.5)
        color = estilo.c("texto") if self.activo else estilo.c("texto2")
        p.drawPixmap(QPointF(14, r.center().y() - 9), estilo.pixmap_icono(self.icono_nombre, color, 18))
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold if self.activo else QFont.Normal)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRectF(44, r.top(), r.width() - 70, r.height()), Qt.AlignLeft | Qt.AlignVCenter, self.texto)
        p.setPen(QPen(estilo.c("texto3"), 1.4))
        x, cy = r.right() - 16, r.center().y()
        p.drawPolyline([QPointF(x - 3, cy - 4), QPointF(x + 1, cy), QPointF(x - 3, cy + 4)])
        p.end()


class _Tema(QWidget):
    """Miniatura del tema (ventana en oscuro, en claro o mitad y mitad) con su círculo de selección."""
    clicked = Signal()

    def __init__(self, nombre, etiqueta, parent=None):
        super().__init__(parent)
        self.nombre, self.etiqueta, self.activo = nombre, etiqueta, False
        self.setFixedSize(132, 112)
        self.setCursor(Qt.PointingHandCursor)

    def poner(self, activo):
        self.activo = activo
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def _ventana(self, p, r, oscuro):
        fondo, barra, linea = (("#17171C", "#26262D", "#3A3A42") if oscuro else ("#FFFFFF", "#EFEFF3", "#D4D4DA"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(fondo))
        p.drawRect(r)
        p.setBrush(QColor(barra))
        p.drawRect(QRectF(r.left(), r.top(), r.width(), 12))
        for i, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(r.left() + 8 + i * 7, r.top() + 6), 2.2, 2.2)
        p.setBrush(QColor(estilo.ROJO))
        p.drawRoundedRect(QRectF(r.left() + 8, r.top() + 20, 30, 8), 3, 3)
        p.setBrush(QColor(linea))
        for i, ancho in enumerate((0.7, 0.5, 0.62)):
            p.drawRoundedRect(QRectF(r.left() + 8, r.top() + 34 + i * 9, r.width() * ancho, 5), 2, 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        caja = QRectF(2, 2, self.width() - 4, 74)
        p.save()
        from PySide6.QtGui import QPainterPath
        camino = QPainterPath()
        camino.addRoundedRect(caja, 10, 10)
        p.setClipPath(camino)
        if self.nombre == "Oscuro":
            self._ventana(p, caja, True)
        elif self.nombre == "Claro":
            self._ventana(p, caja, False)
        else:
            self._ventana(p, caja, True)
            p.setClipRect(QRectF(caja.center().x(), caja.top(), caja.width() / 2, caja.height()))
            p.setClipPath(camino, Qt.IntersectClip)
            self._ventana(p, caja, False)
        p.restore()
        p.setPen(QPen(QColor(estilo.ROJO), 2) if self.activo else QPen(estilo.c("borde2"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(caja, 10, 10)
        cy = 96
        circ = QRectF(self.width() / 2 - 38, cy - 7, 14, 14)
        if self.activo:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(estilo.ROJO))
            p.drawEllipse(circ)
            p.setPen(QPen(QColor("white"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(circ.left() + 3.8, cy), QPointF(circ.left() + 6.2, cy + 2.6),
                            QPointF(circ.right() - 3.5, cy - 2.8)])
        else:
            p.setPen(QPen(estilo.c("borde2"), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(circ)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold if self.activo else QFont.Normal)
        p.setFont(f)
        p.setPen(estilo.c("texto") if self.activo else estilo.c("texto2"))
        p.drawText(QRectF(circ.right() + 8, cy - 10, 80, 20), Qt.AlignLeft | Qt.AlignVCenter, self.etiqueta)
        p.end()


def _fila(icono_nombre, titulo, ayuda="", *controles):
    """Renglón de ajuste: ícono en cuadrito, título, ayuda y los controles a la derecha."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 4, 0, 4)
    h.setSpacing(14)
    h.addWidget(Icono(icono_nombre, 18, fondo="#8A8A93", caja=36), 0, Qt.AlignTop)
    v = QVBoxLayout()
    v.setSpacing(1)
    t = StrongBodyLabel(titulo)
    f = t.font()
    f.setPixelSize(14)
    t.setFont(f)
    v.addWidget(t)
    ayuda_l = CaptionLabel(ayuda)
    ayuda_l.setWordWrap(True)
    v.addWidget(ayuda_l)
    h.addLayout(v, 1)   # primero dentro de la fila: si se muestra sin padre, aparece como ventanita suelta
    ayuda_l.setHidden(not ayuda)
    for c in controles:
        h.addWidget(c, 0, Qt.AlignVCenter)
    w.ayuda = ayuda_l
    return w


class AjustesInterface(QWidget):
    reserva_cambiada = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("ajustes")
        self.cfg = cfg
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(24, 24, 0, 0)
        raiz.setSpacing(18)

        # ---------- menú de secciones ----------
        menu = QWidget()
        menu.setFixedWidth(220)
        vm = QVBoxLayout(menu)
        vm.setContentsMargins(0, 0, 0, 0)
        vm.setSpacing(2)
        cab = QHBoxLayout()
        cab.setSpacing(10)
        cab.addWidget(Icono("ajustes", 22, fondo="#8A8A93", caja=40))
        cab.addWidget(TitleLabel("Ajustes"), 1)
        vm.addLayout(cab)
        vm.addSpacing(14)
        self.items = {}
        for clave, texto, icono_nombre in SECCIONES:
            it = _ItemMenu(texto, icono_nombre)
            it.clicked.connect(lambda c=clave: self.ir_a(c))
            self.items[clave] = it
            vm.addWidget(it)
        vm.addStretch(1)
        self.menu = menu
        raiz.addWidget(menu)

        # ---------- contenido ----------
        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        self.scroll.setWidget(cont)
        raiz.addWidget(self.scroll, 1)
        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 4, 28, 28)
        v.setSpacing(12)
        self.titulo_angosto = TitleLabel("Ajustes")      # cuando el menú de secciones no cabe
        self.titulo_angosto.hide()
        v.addWidget(self.titulo_angosto)
        self.grupos = {}

        # Comprobantes
        self.l_carpeta = None
        b_abrir = PushButton(FIF.FOLDER, "Abrir")
        b_abrir.clicked.connect(self._abrir_carpeta)
        b_cambiar = PushButton("Cambiar…")
        b_cambiar.clicked.connect(self.cambiar_carpeta)
        f_carpeta = _fila("carpeta", "Carpeta de los comprobantes", cfg["carpeta_salida"], b_abrir, b_cambiar)
        self.l_carpeta = f_carpeta.ayuda
        self.reserva = Monto()
        self.reserva.setValue(int(cfg.get("reserva_por_defecto", 600)))
        self.reserva.setFixedWidth(170)
        self.reserva.editingFinished.connect(self.guardar_reserva)
        self.calidad = Slider(Qt.Horizontal)
        self.calidad.setRange(60, motor.CALIDAD_MAX)
        self.calidad.setValue(min(int(cfg.get("calidad_jpg", motor.CALIDAD_POR_DEFECTO)), motor.CALIDAD_MAX))
        self.calidad.setFixedWidth(170)
        self.l_calidad = StrongBodyLabel(str(self.calidad.value()))
        self.l_calidad.setFixedWidth(30)
        self.calidad.valueChanged.connect(lambda n: self.l_calidad.setText(str(n)))
        self.calidad.sliderReleased.connect(self.guardar_calidad)
        self.abrir_carpeta = SwitchButton()
        self.abrir_carpeta.setOnText("")
        self.abrir_carpeta.setOffText("")
        self.abrir_carpeta.setChecked(bool(cfg.get("abrir_carpeta", True)))
        self.abrir_carpeta.checkedChanged.connect(self.cambiar_abrir_carpeta)
        self._grupo(v, "comprobantes", "Comprobantes", [
            f_carpeta,
            _fila("carpeta", "Abrir la carpeta al terminar",
                  "Al generar un comprobante se abre su carpeta con el archivo marcado", self.abrir_carpeta),
            _fila("recibo", "Reserva por defecto", "Monto que se sugiere al crear un comprobante", self.reserva),
            _fila("galeria", "Calidad del JPG", "Más alto = más nítido y más pesado (85 recomendado: el comprobante ya sale al doble de resolución)",
                  self.calidad, self.l_calidad)])

        # Vista previa
        self.animaciones = SwitchButton()
        self.animaciones.setOnText("")          # sin «Sí/No»: tienen anchos distintos y desalineaban
        self.animaciones.setOffText("")
        self.animaciones.setChecked(bool(cfg.get("animaciones", True)))
        self.animaciones.checkedChanged.connect(self.cambiar_animaciones)
        self._grupo(v, "vista", "Movimiento", [   # (la vista previa en vivo está siempre encendida)
            _fila("chispa", "Animaciones",
                  "Transiciones suaves, montos que cuentan y la claqueta al generar (apágalas si prefieres todo quieto)",
                  self.animaciones)])

        # Apariencia
        temas = QWidget()
        ht = QHBoxLayout(temas)
        ht.setContentsMargins(50, 4, 0, 4)
        ht.setSpacing(16)
        self.temas = {}
        for nombre, etiqueta in (("Oscuro", "Oscuro"), ("Claro", "Claro"), ("Automático (como el sistema)", "Sistema")):
            t = _Tema(nombre if nombre != "Automático (como el sistema)" else "Sistema", etiqueta)
            t.clicked.connect(lambda n=nombre: self.cambiar_tema(n))
            self.temas[nombre] = t
            ht.addWidget(t)
        ht.addStretch(1)
        self._grupo(v, "apariencia", "Apariencia", [
            _fila("ajustes", "Tema", "Elige cómo se ve la ventana"), temas], separar=False)
        self._marcar_tema(cfg.get("tema", "Oscuro"))

        # Datos
        b_datos = PushButton(FIF.FOLDER, "Abrir carpeta")
        b_datos.clicked.connect(lambda: abrir(rutas.BASE_DATOS.parent))
        b_exportar = PushButton(FIF.SAVE, "Exportar…")
        b_exportar.clicked.connect(self.exportar_copia)
        self._grupo(v, "datos", "Datos y copias", [
            _fila("personas", "Historial de clientes", str(rutas.BASE_DATOS), b_datos),
            _fila("carpeta", "Copia de seguridad de clientes",
                  "Guarda una copia del historial (clientes y pagos) donde quieras", b_exportar)])

        modo = "Portable (todo se guarda junto al programa)" if rutas.PORTABLE else "Instalado"
        pie = CaptionLabel(f"Comprobantes · Cinema Productions · versión {rutas.VERSION} · {modo}\n"
                           f"Atajos: {CTRL}N nuevo · {CTRL}Enter generar · {CTRL}V pegar captura · {CTRL}F buscar")
        pie.setAlignment(Qt.AlignCenter)
        v.addSpacing(6)
        v.addWidget(pie)
        v.addStretch(1)

        self.scroll.verticalScrollBar().valueChanged.connect(self._seguir_scroll)
        self.items["comprobantes"].poner(True)

    # ---------- armado ----------
    def _grupo(self, v, clave, titulo, filas, separar=True):
        t = StrongBodyLabel(titulo)
        f = t.font()
        f.setPixelSize(15)
        t.setFont(f)
        v.addSpacing(6)
        v.addWidget(t)
        card = Tarjeta()
        c = QVBoxLayout(card)
        c.setContentsMargins(18, 12, 18, 12)
        c.setSpacing(8)
        for i, fila in enumerate(filas):
            if i and separar:
                c.addWidget(Separador())
            c.addWidget(fila)
        v.addWidget(card)
        self.grupos[clave] = t

    def ir_a(self, clave):
        destino = self.grupos[clave].y() - 6
        self.scroll.verticalScrollBar().setValue(max(destino, 0))
        for c, it in self.items.items():
            it.poner(c == clave)

    def _seguir_scroll(self, valor):
        barra = self.scroll.verticalScrollBar()
        actual = next(iter(self.grupos))
        for clave, w in self.grupos.items():
            if w.y() - 40 <= valor:
                actual = clave
        if valor >= barra.maximum() - 4:
            actual = list(self.grupos)[-1]
        for c, it in self.items.items():
            it.poner(c == actual)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.menu.setVisible(self.width() >= 820)
        self.titulo_angosto.setVisible(self.width() < 820)

    def showEvent(self, e):
        super().showEvent(e)
        # el tema marcado es el que se ve (si no hay preferencia guardada, el activo)
        from qfluentwidgets import isDarkTheme
        tema = self.cfg.get("tema") or ("Oscuro" if isDarkTheme() else "Claro")
        self._marcar_tema(tema)

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
            self.l_carpeta.setText(carpeta)

    def guardar_reserva(self):
        self.cfg["reserva_por_defecto"] = self.reserva.value()
        motor.guardar_preferencia("reserva_por_defecto", self.reserva.value())
        self.reserva_cambiada.emit()

    def guardar_calidad(self):
        self.cfg["calidad_jpg"] = self.calidad.value()
        motor.guardar_preferencia("calidad_jpg", self.calidad.value())
        aviso(self, "success", "Calidad del JPG", f"Los próximos comprobantes se guardarán con calidad "
                                                 f"{self.calidad.value()}.")

    def cambiar_abrir_carpeta(self, si):
        self.cfg["abrir_carpeta"] = si
        motor.guardar_preferencia("abrir_carpeta", si)

    def cambiar_animaciones(self, si):
        estilo.ANIMAR = si
        self.cfg["animaciones"] = si
        motor.guardar_preferencia("animaciones", si)

    def _marcar_tema(self, nombre):
        for n, t in self.temas.items():
            t.poner(n == nombre)

    def cambiar_tema(self, nombre):
        self.cfg["tema"] = nombre
        motor.guardar_preferencia("tema", nombre)
        aplicar_tema(nombre)
        self._marcar_tema(nombre)
        QTimer.singleShot(0, lambda: self.window().update())

    def exportar_copia(self):
        sugerido = str(Path.home() / f"Clientes Cinema Productions {date.today():%Y-%m-%d}.db")
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar copia del historial", sugerido,
                                                 "Base de datos (*.db)")
        if not destino:
            return
        try:
            shutil.copy2(rutas.BASE_DATOS, destino)
            aviso(self, "success", "Copia guardada", destino, 6000)
        except OSError as e:
            aviso(self, "error", "No se pudo guardar la copia", str(e), 8000)
