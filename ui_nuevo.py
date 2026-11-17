"""Pantalla «Nuevo comprobante» — vista previa protagonista.

Izquierda: pasos 1·2·3 y tres secciones (cliente y evento · paquete · pago y captura) con su estado.
Derecha: lienzo punteado con la vista previa, que se actualiza sola mientras escribes.
Abajo: barra fija con el saldo y los botones Copiar / WhatsApp / Generar."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QDate, QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CalendarPicker, CaptionLabel, FlowLayout, FluentIcon as FIF,
                            IndeterminateProgressRing, LineEdit, PrimaryPushButton, PushButton,
                            SegmentedWidget, SmoothScrollArea, StrongBodyLabel,
                            TitleLabel, ToolTipFilter, TransparentPushButton, TransparentToolButton,
                            isDarkTheme)

import estilo
import motor
import registro
import rutas
from estilo import Atajo, Cifra, Pildora
from ui_comun import (CTRL, NOMBRES_PAQUETE, Bloque, Monto, Pasos, Rejilla, TarjetaPaquete, Trabajo, ZonaCaptura,
                      abrir, abrir_whatsapp, aviso, copiar_imagen, digitos_telefono, faltan, fecha_larga,
                      formatear_telefono, q)

ANCHO_COMPACTO = 900     # por debajo: se ve el formulario o la vista previa (botón para cambiar), no los dos
ANCHO_BARRA_CORTA = 780  # por debajo: la barra inferior se simplifica
MARGEN_LIENZO = 22       # espacio alrededor del comprobante para su sombra


def _campo(titulo, widget, nota=None):
    """Etiqueta arriba del campo; la nota (p. ej. «sábado · faltan 70 días») va en el mismo renglón
    de la etiqueta, a la derecha, para no gastar un renglón más."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    fila = QHBoxLayout()
    fila.setSpacing(6)
    fila.addWidget(CaptionLabel(titulo))
    fila.addStretch(1)
    if nota is not None:
        fila.addWidget(nota)
    v.addLayout(fila)
    v.addWidget(widget)
    return w


class _FilaServicios(QWidget):
    """Los servicios del paquete en UNA sola fila de píldoras con ícono; los que no caben se resumen
    en «+N» (con la lista completa al pasar el mouse)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.h = QHBoxLayout(self)
        self.h.setContentsMargins(0, 0, 0, 0)
        self.h.setSpacing(6)
        self.h.setSizeConstraint(QHBoxLayout.SetNoConstraint)   # no exige el ancho de todas las píldoras
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.chips, self.nombres = [], []
        self.mas = Pildora("+0")
        self.setFixedHeight(26)

    def minimumSizeHint(self):
        return QSize(0, 26)

    def sizeHint(self):
        return QSize(0, 26)

    def poner(self, incluye):
        while self.h.count():                 # vacía la fila (píldoras, «+N» y el espaciador del final)
            self.h.takeAt(0)
        for c in self.chips:
            c.deleteLater()
        self.chips = [Pildora(t, icono_nombre=i, tam_letra=12, alto=26) for t, _, i in incluye]
        self.nombres = [t for t, _, _ in incluye]
        for c in self.chips:
            self.h.addWidget(c)
        self.h.addWidget(self.mas)
        self.h.addStretch(1)
        self._acomodar()

    def _acomodar(self):
        ancho, usado, ocultos = self.width(), 0, []
        for i, c in enumerate(self.chips):
            resto = len(self.chips) - i - 1
            reserva = 0 if resto == 0 else 50        # lugar para «+N»
            cabe = usado + c.width() + reserva <= ancho and not ocultos
            c.setVisible(cabe)
            if cabe:
                usado += c.width() + 6
            else:
                ocultos.append(self.nombres[i])
        self.mas.setVisible(bool(ocultos))
        if ocultos:
            self.mas.poner(f"+{len(ocultos)}")
            self.mas.setToolTip("También incluye: " + ", ".join(ocultos))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._acomodar()


class _PanelVista(QFrame):
    """Fondo del lado de la vista previa: un poco más claro que la ventana, con una cuadrícula de puntos."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), estilo.c("panel"))
        p.setPen(Qt.NoPen)
        p.setBrush(estilo.c("punto"))
        paso = 22
        for y in range(paso // 2, self.height(), paso):
            for x in range(paso // 2, self.width(), paso):
                p.drawEllipse(QPointF(x, y), 1.1, 1.1)
        p.fillRect(QRectF(0, 0, 1, self.height()), estilo.c("borde"))
        p.end()


class _Lienzo(QWidget):
    """El comprobante flotando sobre el panel, con sombra suave (pintada: no frena la vista en vivo).
    Cada vista nueva entra con un fundido cruzado sobre la anterior; la primera, subiendo suavemente."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None
        self.previo = None
        self._t = 1.0          # 0 → 1: fundido de la imagen anterior a la nueva
        self._entrada = 1.0    # 0 → 1: la primera imagen sube y aparece

    def poner(self, pm):
        anterior = self.pm
        self.pm = pm
        m = MARGEN_LIENZO
        tam = pm.deviceIndependentSize().toSize()
        mismo_tam = anterior is not None and anterior.deviceIndependentSize().toSize() == tam
        self.resize(tam.width() + 2 * m, tam.height() + 2 * m)
        if anterior is None:
            self.previo = None
            estilo.animar(self, "_ani_e", 0.0, 1.0, 420, self._paso_e, QEasingCurve.OutCubic)
        elif mismo_tam and anterior.cacheKey() != pm.cacheKey():
            self.previo = anterior
            estilo.animar(self, "_ani", 0.0, 1.0, 160, self._paso, QEasingCurve.InOutQuad)
        else:
            self.previo = None
            self._t = 1.0
            self.update()

    def _paso(self, v):
        self._t = v
        self.update()

    def _paso_e(self, v):
        self._entrada = v
        self.update()

    def paintEvent(self, e):
        if not self.pm:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = MARGEN_LIENZO
        r = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        if self._entrada < 1:
            p.setOpacity(self._entrada)
            p.translate(0, 14 * (1 - self._entrada))
        p.setPen(Qt.NoPen)
        for i in range(8):                       # sombra: capas cada vez más anchas y tenues
            a = 22 - i * 2.6 if isDarkTheme() else 12 - i * 1.4
            if a <= 0:
                break
            p.setBrush(QColor(0, 0, 0, int(a)))
            g = 2 + i * 2.2
            p.drawRoundedRect(r.adjusted(-g, -g + 6, g, g + 6), 6 + g, 6 + g)
        if self.previo is not None and self._t < 1:
            p.drawPixmap(r.topLeft(), self.previo)
            opacidad = p.opacity()
            p.setOpacity(opacidad * self._t)
            p.drawPixmap(r.topLeft(), self.pm)
            p.setOpacity(opacidad)
        else:
            p.drawPixmap(r.topLeft(), self.pm)
        p.setPen(QPen(estilo.c("borde"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()


class _PildoraVivo(QWidget):
    """«● En vivo» con punto verde que late; clic la apaga («○ En vivo: no»). Misma API que un interruptor."""
    checkedChanged = Signal(bool)

    def __init__(self, encendido=True, parent=None):
        super().__init__(parent)
        self._on = encendido
        self._fase = 0.0
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Vista previa en vivo: clic para encenderla o apagarla")
        self._ani = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1600, loopCount=-1)
        self._ani.setEasingCurve(QEasingCurve.OutCubic)
        self._ani.valueChanged.connect(self._latir)
        self._medir()
        if encendido:
            self._ani.start()

    def _texto(self):
        return "En vivo" if self._on else "En vivo: no"

    def _medir(self):
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        from PySide6.QtGui import QFontMetrics
        self.setFixedWidth(QFontMetrics(f).horizontalAdvance(self._texto()) + 38)

    def _latir(self, v):
        self._fase = v
        self.update()

    def isChecked(self):
        return self._on

    def setChecked(self, si):
        si = bool(si)
        if si == self._on:
            return
        self._on = si
        self._medir()
        if si:
            self._ani.start()
        else:
            self._ani.stop()
        self.update()
        self.checkedChanged.emit(si)

    def mousePressEvent(self, e):
        self.setChecked(not self._on)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        color = QColor(estilo.VERDE) if self._on else estilo.c("texto3")
        p.setPen(QPen(estilo.alfa(color, 90), 1))
        p.setBrush(estilo.alfa(color, 30 if self._on else 14))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        centro = QPointF(15, r.center().y())
        if self._on:
            p.setPen(Qt.NoPen)
            p.setBrush(estilo.alfa(color, int(110 * (1 - self._fase))))
            p.drawEllipse(centro, 3.5 + 5 * self._fase, 3.5 + 5 * self._fase)
            p.setBrush(color)
            p.drawEllipse(centro, 3.6, 3.6)
        else:
            p.setPen(QPen(color, 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(centro, 3.4, 3.4)
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(estilo.c("texto") if self._on else estilo.c("texto3"))
        p.drawText(QRectF(26, 0, self.width() - 30, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self._texto())
        p.end()


class _Aviso(QWidget):
    """Tarjeta flotante sobre la vista previa con una animación de Higgsfield: la claqueta mientras
    PhotoCraft crea el comprobante, y el ✓ con destellos cuando queda listo. Aparece subiendo y se desvanece."""

    def __init__(self, nombre, una_vez, parent):
        super().__init__(parent)
        self.anim = estilo.Animacion(nombre, 128, una_vez)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 16, 26, 18)
        v.setSpacing(2)
        v.addWidget(self.anim, 0, Qt.AlignHCenter)
        self.texto = StrongBodyLabel("")
        self.texto.setAlignment(Qt.AlignCenter)
        f = self.texto.font()
        f.setPixelSize(16)
        self.texto.setFont(f)
        v.addWidget(self.texto)
        self.sub = CaptionLabel("")
        self.sub.setAlignment(Qt.AlignCenter)
        v.addWidget(self.sub)
        self.efecto = QGraphicsOpacityEffect(self)
        self.efecto.setOpacity(0.0)
        self.setGraphicsEffect(self.efecto)
        self._sube = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(estilo.c("borde2"), 1))
        p.setBrush(self.anim.fondo)
        p.drawRoundedRect(r, 20, 20)
        p.end()

    def centrar(self):
        if not self.parent():
            return
        self.adjustSize()
        pr = self.parent().rect()
        self.move(int((pr.width() - self.width()) / 2), int((pr.height() - self.height()) / 2 + 18 * (1 - self._sube)))

    def _paso(self, v):
        self._sube = v
        self.efecto.setOpacity(v)
        self.centrar()

    def mostrar(self, texto, sub="", ms_visible=None):
        self.texto.setText(texto)
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        self.centrar()
        self.show()
        self.raise_()
        self.anim.iniciar()
        estilo.animar(self, "_ani", self.efecto.opacity(), 1.0, 300, self._paso, QEasingCurve.OutBack)
        if ms_visible:
            QTimer.singleShot(ms_visible, self.ocultar)

    def ocultar(self):
        if not self.isVisible():
            return

        def fin():
            self.hide()
            self.anim.detener()
        estilo.animar(self, "_ani", self.efecto.opacity(), 0.0, 260,
                      lambda v: self.efecto.setOpacity(v), QEasingCurve.InCubic, fin)


class _Barra(QFrame):
    """Barra fija inferior: superficie con línea arriba."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), estilo.c("sup"))
        p.fillRect(QRectF(0, 0, self.width(), 1), estilo.c("borde"))
        p.end()


class NuevoInterface(QWidget):
    registrado = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("nuevo")
        self.cfg = cfg
        self.paquete = next(iter(cfg["paquetes"]))
        self.evento = next(iter(cfg["eventos"]))
        self.ultimo = None          # último comprobante generado (JPG final)
        self.cliente_id = None      # para corregir sin duplicar si se vuelve a generar
        self.sin_generar = False    # hubo cambios después de generar
        self.trabajo = None
        self.vista_trabajo = None   # el último hilo de vista lanzado
        self.vista_ocupada = False  # hay una vista en camino (hasta que llega listo/fallo)
        self.vista_pendiente = False
        self._hilos_vista = set()   # hilos vivos: se sueltan recién cuando terminan del todo
        self.vista_ruta = None
        self.n_vista = 0
        self.zoom = False
        self.compacto = None
        self.viendo_vista = False
        self.apretado = False       # ventana baja: formulario con menos aire para que quepa sin scroll
        self._alto_normal = 0

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        cuerpo = self.cuerpo = QHBoxLayout()
        cuerpo.setSpacing(0)
        raiz.addLayout(cuerpo, 1)

        # ================= Formulario =================
        scroll = self.scroll_form = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        v = self.v_form = QVBoxLayout(cont)
        v.setContentsMargins(26, 16, 20, 14)
        v.setSpacing(10)

        cab = QHBoxLayout()
        cab.addWidget(TitleLabel("Nuevo comprobante"), 1)
        b_limpiar = PushButton(FIF.BROOM, "Limpiar")
        b_limpiar.setToolTip(f"Empezar un comprobante nuevo ({CTRL}N)")
        b_limpiar.installEventFilter(ToolTipFilter(b_limpiar))
        b_limpiar.clicked.connect(self.limpiar)
        cab.addWidget(b_limpiar, 0, Qt.AlignVCenter)
        self.b_ver_vista = PushButton(FIF.VIEW, "Vista previa")      # solo en ventanas angostas
        self.b_ver_vista.clicked.connect(lambda: self._ver_vista(True))
        cab.addWidget(self.b_ver_vista, 0, Qt.AlignVCenter)
        v.addLayout(cab)
        self.pasos = Pasos(["Cliente y evento", "Paquete", "Pago y captura"])
        self.pasos.elegido.connect(lambda i: self.abrir_bloque(self.bloques[i]))
        v.addWidget(self.pasos)
        self.progreso = CaptionLabel("")      # (lo que falta va en las píldoras y en el tooltip de los pasos)
        self.progreso.hide()

        # ---- ① Cliente y evento ----
        self.b1 = Bloque(1, "Cliente y evento", "personas")
        self.seg = SegmentedWidget()
        for nombre in cfg["eventos"]:
            self.seg.addItem(nombre, nombre, onClick=lambda n=nombre: self._evento(n))
        self.seg.setCurrentItem(self.evento)
        self.seg.setFixedWidth(190)
        self.b1.en_cabecera(self.seg)
        self.festejado = LineEdit()
        self.festejado.setPlaceholderText("Ej. Ana y Luis  /  Sofía Martínez")
        self.festejado.setClearButtonEnabled(True)
        self.lugar = LineEdit()
        self.lugar.setPlaceholderText("Ej. Hotel Camino Real, Guatemala")
        self.lugar.setClearButtonEnabled(True)
        self.fecha_evento = CalendarPicker()
        self.fecha_evento.setDateFormat("dd/MM/yyyy")
        self.fecha_evento.setDate(QDate.currentDate())
        self.nota_fecha = CaptionLabel("")
        self.telefono = LineEdit()
        self.telefono.setText("+502 ")
        self.telefono.setPlaceholderText("+502 0000 0000")
        for campo in (self.festejado, self.lugar):  # al salir del campo, que se vea desde el inicio
            campo.editingFinished.connect(lambda c=campo: c.setCursorPosition(0))
        self.telefono.editingFinished.connect(
            lambda: self.telefono.setText(formatear_telefono(self.telefono.text())))
        self.nota_fecha.setWordWrap(True)
        self.b1.cuerpo.addWidget(Rejilla([
            _campo("Festejado(s)", self.festejado), _campo("Lugar", self.lugar),
            _campo("Fecha del evento", self.fecha_evento, self.nota_fecha),
            _campo("Teléfono del cliente (WhatsApp)", self.telefono)], max_columnas=2, ancho_min=180))
        v.addWidget(self.b1)

        # ---- ② Paquete ----
        self.b2 = Bloque(2, "Paquete", "corona")
        self.tarjetas = {}
        destacado = cfg.get("paquete_destacado", "COMPLETO")
        for clave, paq in cfg["paquetes"].items():
            t = TarjetaPaquete(clave, paq, destacado=(clave == destacado))
            t.elegida.connect(self.elegir_paquete)
            self.tarjetas[clave] = t
        self.b2.cuerpo.addWidget(Rejilla(list(self.tarjetas.values()), max_columnas=4, ancho_min=98, espacio=8,
                                         validas=(1, 2, 4)))
        self.servicios = _FilaServicios()
        self.b2.cuerpo.addWidget(self.servicios)
        v.addWidget(self.b2)

        # ---- ③ Pago y captura ----
        self.b3 = Bloque(3, "Pago y captura", "recibo")
        self.total = Monto()
        self.reserva = Monto()
        self.fecha_pago = CalendarPicker()
        self.fecha_pago.setDateFormat("dd/MM/yyyy")
        self.fecha_pago.setDate(QDate.currentDate())
        self.b3.cuerpo.addWidget(Rejilla([
            _campo("Precio del paquete", self.total), _campo("Reserva / anticipo", self.reserva),
            _campo("Fecha del pago", self.fecha_pago)], max_columnas=3, ancho_min=128))
        self.zona = ZonaCaptura(100)          # clic para buscarla, arrastrar o Ctrl+V: no hacen falta botones
        self.b3.cuerpo.addWidget(self.zona)
        v.addWidget(self.b3)
        v.addStretch(1)

        self.bloques = [self.b1, self.b2, self.b3]
        for b in self.bloques:
            b.pedir_abrir.connect(self.abrir_bloque)
        cuerpo.addWidget(scroll, 44)

        # ================= Vista previa protagonista =================
        panel = self.panel_vista = _PanelVista()
        p = QVBoxLayout(panel)
        p.setContentsMargins(22, 18, 22, 10)
        p.setSpacing(6)
        cabv = QHBoxLayout()
        cabv.setSpacing(10)
        self.b_volver = TransparentPushButton(FIF.LEFT_ARROW, "Datos")     # solo en ventanas angostas
        self.b_volver.clicked.connect(lambda: self._ver_vista(False))
        cabv.addWidget(self.b_volver)
        self.titulo_vista = StrongBodyLabel("Vista previa en vivo")
        f = self.titulo_vista.font()
        f.setPixelSize(15)
        self.titulo_vista.setFont(f)
        cabv.addWidget(self.titulo_vista)
        self.en_vivo = _PildoraVivo(bool(cfg.get("vista_en_vivo", True)))
        self.en_vivo.checkedChanged.connect(self._cambiar_en_vivo)
        cabv.addWidget(self.en_vivo)
        self.ring = IndeterminateProgressRing()
        self.ring.setFixedSize(18, 18)
        self.ring.setStrokeWidth(3)
        self.ring.hide()
        cabv.addWidget(self.ring)
        cabv.addStretch(1)
        self.b_zoom = TransparentToolButton(FIF.ZOOM_IN)
        self.b_zoom.setToolTip("Ampliar / ajustar a la ventana")
        self.b_zoom.installEventFilter(ToolTipFilter(self.b_zoom))
        self.b_zoom.clicked.connect(self._alternar_zoom)
        self.b_ext = TransparentToolButton(FIF.FULL_SCREEN)
        self.b_ext.setToolTip("Abrir en el visor de imágenes")
        self.b_ext.installEventFilter(ToolTipFilter(self.b_ext))
        self.b_ext.clicked.connect(lambda: abrir(self._imagen_actual()))
        cabv.addWidget(self.b_zoom)
        cabv.addWidget(self.b_ext)
        p.addLayout(cabv)
        self.estado = CaptionLabel("")
        self.estado.setWordWrap(True)
        p.addWidget(self.estado)
        self.area = SmoothScrollArea()
        self.area.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self.area.viewport().setStyleSheet("background:transparent")
        self.area.setAlignment(Qt.AlignCenter)
        self.lienzo = _Lienzo()
        self.lienzo.setStyleSheet("background:transparent")
        self.area.setWidget(self.lienzo)
        self.area.setWidgetResizable(False)
        p.addWidget(self.area, 1)
        cuerpo.addWidget(panel, 56)
        self.aviso_cargando = _Aviso("cargando", False, panel)   # animaciones de Higgsfield sobre la vista
        self.aviso_listo = _Aviso("listo", True, panel)

        # ================= Barra fija inferior =================
        barra = _Barra()
        barra.setFixedHeight(74)
        hb = self.hb_barra = QHBoxLayout(barra)
        hb.setContentsMargins(28, 10, 22, 10)
        hb.setSpacing(10)
        sv = QVBoxLayout()
        sv.setSpacing(0)
        sv.addStretch(1)
        sv.addWidget(CaptionLabel("Saldo pendiente"))
        self.saldo = Cifra("Q0", 30, estilo.ROJO)
        sv.addWidget(self.saldo)
        sv.addStretch(1)
        hb.addLayout(sv)
        hb.addSpacing(18)
        self.resumen = CaptionLabel("")
        self.resumen.setWordWrap(True)
        self.resumen.setMinimumWidth(0)
        hb.addWidget(self.resumen, 1)
        self.btn_copiar = PushButton(FIF.COPY, "Copiar")
        self.btn_copiar.setFixedHeight(38)
        self.btn_copiar.clicked.connect(self.copiar)
        self.btn_wa = PushButton(FIF.CHAT.icon(color=QColor(estilo.VERDE)), "WhatsApp")
        self.btn_wa.setFixedHeight(38)
        self.btn_wa.setToolTip("Abre el chat del cliente; el comprobante queda copiado para pegar")
        self.btn_wa.installEventFilter(ToolTipFilter(self.btn_wa))
        self.btn_wa.clicked.connect(self.whatsapp)
        self.atajo = Atajo(f"{CTRL}Enter")
        self.btn_generar = PrimaryPushButton(FIF.ACCEPT, "Generar comprobante")
        self.btn_generar.setToolTip(f"{CTRL}Enter")
        self.btn_generar.installEventFilter(ToolTipFilter(self.btn_generar))
        self.btn_generar.setFixedHeight(42)
        self.btn_generar.setMinimumWidth(220)
        self.btn_generar.clicked.connect(self.generar)
        hb.addWidget(self.btn_copiar)
        hb.addWidget(self.btn_wa)
        hb.addSpacing(6)
        self.atajo.setFixedHeight(24)
        hb.addWidget(self.atajo, 0, Qt.AlignVCenter)
        hb.addWidget(self.btn_generar)
        raiz.addWidget(barra)

        # ================= Señales =================
        # Vista en vivo: cada tecla pide la vista casi de inmediato (30 ms juntan los cambios que llegan
        # a la vez, p. ej. al pegar o limpiar). Si PhotoCraft aún pinta la anterior, la nueva espera su
        # turno con los datos más recientes; el tope evita que una racha de teclas la posponga.
        self.temporizador = QTimer(self)
        self.temporizador.setSingleShot(True)
        self.temporizador.setInterval(30)
        self.temporizador.timeout.connect(self._render_vista)
        self.tope_vista = QTimer(self)
        self.tope_vista.setSingleShot(True)
        self.tope_vista.setInterval(200)
        self.tope_vista.timeout.connect(self._render_vista)
        self.aviso_ring = QTimer(self)   # el anillo solo aparece si la vista tarda (sin parpadeos)
        self.aviso_ring.setSingleShot(True)
        self.aviso_ring.setInterval(450)
        self.aviso_ring.timeout.connect(self.ring.show)
        for s in (self.festejado.textChanged, self.lugar.textChanged, self.telefono.textChanged,
                  self.fecha_evento.dateChanged, self.fecha_pago.dateChanged, self.total.valueChanged,
                  self.reserva.valueChanged, self.zona.cambiada):
            s.connect(self._cambio)

        self.reserva.setValue(int(cfg.get("reserva_por_defecto", 600)))
        self.elegir_paquete(self.paquete, desde_usuario=False)
        self.abrir_bloque(self.b1)
        self._botones_resultado()
        self._mostrar_plantilla()
        self._cambio(programar=False)

    # ================= Bloques y estado =================
    def abrir_bloque(self, bloque):
        """Las secciones están siempre abiertas: se resalta la pedida y se lleva a la vista."""
        for b in self.bloques:
            b.abrir(b is bloque)
        QTimer.singleShot(0, lambda: self.scroll_form.ensureWidgetVisible(bloque, 0, 16))
        if bloque is self.b1:
            self.festejado.setFocus()

    def _evento(self, nombre):
        self.evento = nombre
        self._cambio()

    def elegir_paquete(self, clave, desde_usuario=True):
        self.paquete = clave
        paq = self.cfg["paquetes"][clave]
        for k, t in self.tarjetas.items():
            t.marcar(k == clave)
        self.servicios.poner(paq.get("incluye", []))
        self.total.setValue(int(paq["precio"]))
        if desde_usuario:
            self._cambio()
            if not self.en_vivo.isChecked() and not (self.ultimo and not self.sin_generar):
                self._mostrar_plantilla()      # sin vista en vivo: al menos la plantilla del paquete elegido

    def actualizar_precios(self):
        for clave, t in self.tarjetas.items():
            t.actualizar_precio(self.cfg["paquetes"][clave]["precio"])
        self.elegir_paquete(self.paquete)

    def _estado_bloques(self):
        fe = self.fecha_evento.getDate().toPython()
        self.nota_fecha.setText(f"{fecha_larga(fe).split(' ')[0]} · {faltan(fe)}")
        self.nota_fecha.setToolTip(fecha_larga(fe).capitalize())
        f1 = [n for n, ok in (("festejado", self.festejado.text().strip()),
                              ("lugar", self.lugar.text().strip()),
                              ("teléfono", len(digitos_telefono(self.telefono.text())) >= 10)) if not ok]
        self.b1.poner_estado(not f1, " · ".join(x for x in (
            self.festejado.text().strip() or "Sin nombre", self.lugar.text().strip(),
            fe.strftime("%d/%m/%Y"), self.telefono.text().strip(), self.evento) if x),
            falta=f1[0] if len(f1) == 1 else (f"{len(f1)} datos" if f1 else None))
        paq = self.cfg["paquetes"][self.paquete]
        self.b2.poner_estado(True, f"{NOMBRES_PAQUETE.get(self.paquete, self.paquete)} · {q(self.total.value())} · "
                                   f"{len(paq.get('incluye', []))} servicios")
        f3 = []
        if not self.zona.ruta:
            f3.append("captura del pago")
        if self.reserva.value() > self.total.value():
            f3.append("la reserva es mayor que el precio")
        self.b3.poner_estado(not f3, f"Reserva {q(self.reserva.value())} · "
                                     f"{self.fecha_pago.getDate().toPython().strftime('%d/%m/%Y')} · "
                                     f"captura {'✓' if self.zona.ruta else 'pendiente'}",
                             falta=("captura" if not self.zona.ruta else "revisar reserva") if f3 else None)
        faltantes = f1 + f3
        listos = sum(b.completo for b in self.bloques)
        self.pasos.poner([b.completo for b in self.bloques])
        self.progreso.setText(f"{listos} de 3 listos" + (f" · falta: {', '.join(faltantes)}" if faltantes else
                                                        " · todo listo para generar"))
        self.pasos.setToolTip(self.progreso.text())
        self.saldo.poner_numero(int(max(self.total.value() - self.reserva.value(), 0)), q)
        self.resumen.setText(f"{NOMBRES_PAQUETE.get(self.paquete, self.paquete)} · Total {q(self.total.value())}"
                             f" · Reserva {q(self.reserva.value())}")
        return f1, f3

    def _cambio(self, *_, programar=True):
        self._estado_bloques()
        if self.ultimo and programar:
            self.sin_generar = True
            self._botones_resultado()
            self.estado.setText("Hay cambios sin generar · el comprobante guardado es el anterior")
        if programar and self.en_vivo.isChecked():
            self.temporizador.start()
            if not self.tope_vista.isActive():
                self.tope_vista.start()

    # ================= Vista previa =================
    def poner_en_vivo(self, si):
        if self.en_vivo.isChecked() != si:
            self.en_vivo.setChecked(si)

    def _cambiar_en_vivo(self, si):
        self.cfg["vista_en_vivo"] = si
        motor.guardar_preferencia("vista_en_vivo", si)
        if si:
            self._render_vista()
        else:
            self.estado.setText("Vista en vivo apagada · el comprobante se verá al generarlo")

    def _datos(self, para_vista=False):
        total, monto = self.total.value(), self.reserva.value()
        return dict(
            evento=self.evento, paquete=self.paquete,
            festejado=self.festejado.text().strip() or ("Nombre del festejado" if para_vista else ""),
            lugar=self.lugar.text().strip() or ("Lugar" if para_vista else ""),
            fecha_evento=self.fecha_evento.getDate().toPython(),
            fecha_comprobante=self.fecha_pago.getDate().toPython(),
            contacto=formatear_telefono(self.telefono.text()) if len(digitos_telefono(self.telefono.text())) >= 10
            else ("+502 0000 0000" if para_vista else self.telefono.text()),
            total=total, monto=monto, saldo=max(total - monto, 0),
            concepto="RESERVA CON" if monto < total else "PAGO FINAL", captura=self.zona.ruta)

    def _render_vista(self):
        self.temporizador.stop()
        self.tope_vista.stop()
        if not self.en_vivo.isChecked():
            return
        # Bandera propia y no isRunning(): «listo» llega cuando el hilo aún no termina run(), y con
        # isRunning() la vista siguiente quedaba en espera sin que nadie la lanzara (vista congelada).
        if self.vista_ocupada:
            self.vista_pendiente = True
            return
        self.vista_pendiente = False
        self.vista_ocupada = True
        self.n_vista += 1
        destino = Path(tempfile.gettempdir()) / f"cinema_vista_{self.n_vista % 2}.jpg"
        self.aviso_ring.start()
        if self.vista_ruta is None and (not self.ultimo or self.sin_generar):
            self.estado.setText("Preparando la vista previa…")
        hilo = Trabajo(self._datos(para_vista=True), self.cfg, destino=str(destino), calidad=80,
                       vista=True, lado=self._lado_vista())
        hilo.listo.connect(self._vista_lista)
        hilo.fallo.connect(self._vista_fallo)
        hilo.finished.connect(lambda h=hilo: self._hilo_vista_terminado(h))
        self._hilos_vista.add(hilo)
        self.vista_trabajo = hilo
        hilo.start()

    def _hilo_vista_terminado(self, hilo):
        hilo.wait()   # ya está saliendo de run(): así no se destruye un QThread vivo
        self._hilos_vista.discard(hilo)
        if hilo is self.vista_trabajo and self.vista_ocupada:   # terminó sin avisar listo/fallo
            self.vista_ocupada = False
            self._parar_ring()
            if self.vista_pendiente:
                self._render_vista()

    def _vista_lista(self, ruta):
        self.vista_ocupada = False
        if self.ultimo and not self.sin_generar:
            self._parar_ring()
            return  # se está mostrando el comprobante final
        # se muestra aunque ya haya otro cambio en cola: así se ve avanzar mientras escribes
        self.vista_ruta = ruta
        self.titulo_vista.setText("Vista previa en vivo")
        texto = (("Hay cambios sin generar · " if self.sin_generar else "") +
                 "Así quedará · se actualiza mientras escribes")
        if self.estado.text() != texto:
            self.estado.setText(texto)
        self._poner_imagen(ruta)
        if self.vista_pendiente:
            self._render_vista()
        else:
            self._parar_ring()

    def _parar_ring(self):
        self.aviso_ring.stop()
        self.ring.hide()

    def _vista_fallo(self, msg):
        self.vista_ocupada = False
        self._parar_ring()
        if self.vista_pendiente:   # el dato cambió mientras tanto: se reintenta con el nuevo
            self._render_vista()
            return
        self.estado.setText("No se pudo actualizar la vista previa: " + msg.splitlines()[0])

    def _mostrar_plantilla(self):
        vista = rutas.recurso(f"PLANTILLAS/VISTA PREVIA - {self.paquete}.jpg")
        self.estado.setText("Plantilla del paquete · se actualizará con tus datos")
        if Path(vista).exists():
            self._poner_imagen(vista)

    def _imagen_actual(self):
        if self.ultimo and not self.sin_generar:
            return self.ultimo
        return self.vista_ruta

    def _poner_imagen(self, ruta):
        # QImage y no QPixmap(ruta): QPixmap guarda en caché por nombre y hora (en segundos) y,
        # con la vista en vivo rápida, podía mostrar la imagen anterior del mismo archivo.
        self.pix = QPixmap.fromImage(QImage(str(ruta)))
        self._ajustar_imagen()

    def _lado_vista(self):
        """Lado mayor (en píxeles reales) que necesita la vista para verse nítida en este panel:
        PhotoCraft la pinta de ese tamaño y no más grande (así tarda menos)."""
        vp = self.area.viewport().size()
        m = 2 * MARGEN_LIENZO
        prop = 3508 / 2480   # las plantillas son A4 vertical
        ancho = max(vp.width() - m, 400) * (1.8 if self.zoom else 1)
        alto = ancho * prop if self.zoom else min(max(vp.height() - m, 400), ancho * prop)
        return int(max(600, min(alto * self.devicePixelRatioF(), motor.SesionPhotoCraft.LADO_MAX)))

    def _ajustar_imagen(self):
        if not getattr(self, "pix", None) or self.pix.isNull() or not self.panel_vista.isVisible():
            return
        vp = self.area.viewport().size()
        m = 2 * MARGEN_LIENZO
        dpr = self.devicePixelRatioF()          # pantallas Retina / 4K: la imagen se escala a sus píxeles reales
        if self.zoom:
            ancho = max(vp.width() - m, 400) * 1.8
            img = self.pix.scaledToWidth(int(ancho * dpr), Qt.SmoothTransformation)
        else:
            img = self.pix.scaled(int(max(vp.width() - m, 60) * dpr), int(max(vp.height() - m, 60) * dpr),
                                  Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img.setDevicePixelRatio(dpr)
        self.lienzo.poner(img)
        for aviso in (self.aviso_cargando, self.aviso_listo):
            if aviso.isVisible():
                aviso.centrar()
        if (self.en_vivo.isChecked() and self.vista_ruta and self._imagen_actual() == self.vista_ruta
                and max(self.pix.width(), self.pix.height()) + 48 < self._lado_vista()):
            self.temporizador.start()   # la ventana creció o hay zoom: pedir la vista más nítida

    def _alternar_zoom(self):
        self.zoom = not self.zoom
        self.b_zoom.setIcon(FIF.ZOOM_OUT if self.zoom else FIF.ZOOM_IN)
        self._ajustar_imagen()

    # ================= Tamaño de la ventana =================
    def _revisar_alto(self):
        """Todo el formulario debe verse sin desplazarse. Si no cabe en el alto de la ventana se aprieta
        (sin pasos ni fila de servicios, que ya muestran las píldoras y la vista previa; captura en un
        renglón); cuando vuelve a sobrar lugar, regresa a lo normal."""
        if not self.scroll_form.isVisible():
            return
        sb = self.scroll_form.verticalScrollBar()
        alto = self.scroll_form.viewport().height()
        if not self.apretado and sb.maximum() > 0:
            self._alto_normal = alto + sb.maximum()
            self._apretar(True)
        elif self.apretado and alto >= self._alto_normal + 8:
            self._apretar(False)

    def _apretar(self, si):
        self.apretado = si
        self.pasos.setVisible(not si)
        self.servicios.setVisible(not si)
        self.zona.setFixedHeight(62 if si else 100)
        for b in self.bloques:
            b.apretar(si)
        izq, der = (16, 14) if self.compacto else (26, 20)
        self.v_form.setContentsMargins(izq, 8 if si else (12 if self.compacto else 16), der, 6 if si else 14)
        self.v_form.setSpacing(8 if si else 10)

    def _ver_vista(self, si):
        """En ventanas angostas se ve el formulario o la vista previa; este botón alterna."""
        self.viendo_vista = si
        self._acomodar()

    def _acomodar(self):
        ancho = self.width()
        compacto = ancho < ANCHO_COMPACTO
        if compacto != self.compacto:
            self.compacto = compacto
            self.b_ver_vista.setVisible(compacto)
            self.b_volver.setVisible(compacto)
            self.v_form.setContentsMargins(*((16, 12, 14, 12) if compacto else (26, 16, 20, 14)))
        self.scroll_form.setVisible(not compacto or not self.viendo_vista)
        self.panel_vista.setVisible(not compacto or self.viendo_vista)
        # en ventanas medianas el formulario se lleva la mitad: así los 4 paquetes van en una fila
        mitad = ancho < 1300
        self.cuerpo.setStretchFactor(self.scroll_form, 50 if mitad else 44)
        self.cuerpo.setStretchFactor(self.panel_vista, 50 if mitad else 56)
        QTimer.singleShot(40, self._revisar_alto)
        corta = ancho < ANCHO_BARRA_CORTA
        self.resumen.setVisible(ancho >= 1060)
        self.atajo.setVisible(ancho >= 960)
        self.hb_barra.setContentsMargins(*((16, 8, 12, 8) if corta else (28, 10, 22, 10)))
        self.btn_generar.setText("Generar" if corta else "Generar comprobante")
        self.btn_generar.setMinimumWidth(130 if corta else 220)
        QTimer.singleShot(0, self._ajustar_imagen)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._acomodar()

    def showEvent(self, e):
        super().showEvent(e)
        self._acomodar()

    # ================= Acciones =================
    def _botones_resultado(self):
        activo = bool(self.ultimo) and not self.sin_generar
        self.btn_copiar.setEnabled(activo)
        self.btn_wa.setEnabled(activo)

    def copiar(self):
        if self.ultimo:
            copiar_imagen(self.ultimo)
            aviso(self, "success", "Copiado", f"Pégalo en WhatsApp con {CTRL}V.")

    def whatsapp(self):
        if not self.ultimo:
            return
        copiar_imagen(self.ultimo)
        if abrir_whatsapp(self.telefono.text(), self.festejado.text()):
            aviso(self, "success", "WhatsApp", f"Se abrió el chat del cliente. Pega el comprobante con {CTRL}V.", 6000)
        else:
            aviso(self, "warning", "Teléfono", "Revisa el teléfono del cliente (8 dígitos).")

    def pegar(self):
        self.abrir_bloque(self.b3)
        self.zona.pegar()

    def limpiar(self):
        self.festejado.clear()
        self.lugar.clear()
        self.telefono.setText("+502 ")
        self.fecha_evento.setDate(QDate.currentDate())
        self.fecha_pago.setDate(QDate.currentDate())
        self.reserva.setValue(int(self.cfg.get("reserva_por_defecto", 600)))
        self.zona.limpiar()
        self.ultimo = None
        self.cliente_id = None
        self.sin_generar = False
        self._botones_resultado()
        self.elegir_paquete(self.paquete, desde_usuario=False)
        self.abrir_bloque(self.b1)
        self._estado_bloques()
        self._mostrar_plantilla()
        self.titulo_vista.setText("Vista previa en vivo")
        self._ver_vista(False)

    def generar(self):
        f1, f3 = self._estado_bloques()
        if f1 or f3:
            if self.compacto:
                self._ver_vista(False)
            self.abrir_bloque(self.b1 if f1 else self.b3)
            self.zona.marcar_error("captura del pago" in f3)
            aviso(self, "warning", "Faltan datos", "Completa: " + ", ".join(f1 + f3) + ".")
            return
        self.telefono.setText(formatear_telefono(self.telefono.text()))
        self.datos = self._datos()
        self.btn_generar.setEnabled(False)
        self.btn_generar.setText("Generando…")
        self.ring.show()
        self.estado.setText("PhotoCraft está creando el comprobante…")
        if self.compacto:
            self._ver_vista(True)
        self.aviso_listo.hide()
        self.aviso_cargando.mostrar("Creando el comprobante…", "PhotoCraft está armando el JPG")
        self.trabajo = Trabajo(self.datos, self.cfg)
        self.trabajo.listo.connect(self._listo)
        self.trabajo.fallo.connect(self._fallo)
        self.trabajo.start()

    def _fin(self):
        self.btn_generar.setEnabled(True)
        self.ring.hide()
        self.aviso_cargando.ocultar()
        self._acomodar()

    def _listo(self, ruta):
        self._fin()
        d = self.datos
        concepto = motor.CONCEPTOS.get(d["concepto"], d["concepto"]).title()
        corregido = self.cliente_id is not None
        if corregido:
            registro.corregir_reserva(self.cliente_id, d["festejado"], d["contacto"], d["evento"], d["paquete"],
                                      d["lugar"], d["fecha_evento"], d["total"], d["fecha_comprobante"],
                                      d["monto"], concepto, ruta)
        else:
            self.cliente_id = registro.nuevo_cliente(d["festejado"], d["contacto"], d["evento"], d["paquete"],
                                                     d["lugar"], d["fecha_evento"], d["total"])
            registro.agregar_pago(self.cliente_id, d["fecha_comprobante"], d["monto"], concepto, ruta)
        self.registrado.emit()
        self.ultimo = ruta
        self.sin_generar = False
        self._botones_resultado()
        self.titulo_vista.setText("Comprobante generado")
        self.estado.setText(Path(ruta).name)
        if self.compacto:
            self._ver_vista(True)       # en ventanas angostas se muestra el comprobante terminado
        self._poner_imagen(ruta)
        copiar_imagen(ruta)
        self.aviso_listo.mostrar("¡Comprobante corregido!" if corregido else "¡Comprobante listo!",
                                 f"Guardado y copiado · pégalo en WhatsApp con {CTRL}V", 2600)
        aviso(self, "success", "Comprobante corregido" if corregido else "Comprobante listo",
              f"Guardado y copiado: pégalo en WhatsApp con {CTRL}V.", 7000, ruta_abrir=ruta)

    def _fallo(self, msg):
        self._fin()
        self.estado.setText("No se pudo generar.")
        aviso(self, "error", "Error", msg, 10000)
