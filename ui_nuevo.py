"""Pantalla «Nuevo comprobante» — vista previa protagonista.

Izquierda: pasos 1·2·3 y tres secciones (cliente y evento · paquete · pago y captura) con su estado.
Derecha: lienzo punteado con la vista previa, que se actualiza sola mientras escribes.
Abajo: barra fija con el saldo y los botones Copiar / WhatsApp / Generar."""
import math
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import (QAbstractAnimation, QDate, QEasingCurve, QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (Action, CaptionLabel, FlowLayout, FluentIcon as FIF, RoundMenu,
                            IndeterminateProgressRing, LineEdit, PrimaryPushButton, PushButton, Slider,
                            SegmentedWidget, SmoothScrollArea, StrongBodyLabel,
                            TitleLabel, ToolTipFilter, TransparentPushButton, TransparentToolButton,
                            isDarkTheme)

import estilo
import motor
from lista import MAX_SERVICIOS
import registro
import rutas
from estilo import Atajo, Cifra, Pildora
from ui_comun import (CTRL, NOMBRES_PAQUETE, Bloque, CampoFecha, Monto, Pasos, Rejilla, TarjetaPaquete, Trabajo, ZonaCaptura,
                      servicio_legible,
                      abrir, abrir_carpeta_si_toca, abrir_whatsapp, aviso, copiar_imagen, digitos_telefono, faltan, fecha_larga,
                      formatear_telefono, q)

ANCHO_COMPACTO = 900     # por debajo: se ve el formulario o la vista previa (botón para cambiar), no los dos
ANCHO_BARRA_CORTA = 780  # por debajo: la barra inferior se simplifica
MARGEN_LIENZO = 22       # espacio alrededor del comprobante para su sombra
ZOOM_MIN, ZOOM_MAX = 1.0, 4.0   # zoom de la vista previa: 1 = ajustada al panel


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
        self.chips = [Pildora(servicio_legible(t, d)[0], icono_nombre=i, tam_letra=12, alto=26) for t, d, i in incluye]
        self.nombres = [servicio_legible(t, d)[0] for t, d, _ in incluye]
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


class _ChipExtra(QWidget):
    """Un extra agregado a este comprobante: «Cabina 360 · 2 horas · Q1,500» con ✕ para quitarlo."""
    quitar = Signal()

    def __init__(self, texto, icono, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(Pildora(texto, estilo.ROJO, icono_nombre=icono, tam_letra=12, alto=30))
        x = TransparentToolButton(FIF.CLOSE)
        x.setFixedSize(26, 26)
        x.setIconSize(QSize(10, 10))
        x.setToolTip("Quitar este extra")
        x.installEventFilter(ToolTipFilter(x))
        x.clicked.connect(self.quitar)
        h.addWidget(x)


class _Desvanecido(QWidget):
    """Degradado al pie del formulario cuando hay más abajo (ventanas muy bajas): avisa que se puede desplazar."""

    def __init__(self, scroll):
        super().__init__(scroll)
        self.scroll = scroll
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        sb = scroll.verticalScrollBar()
        sb.rangeChanged.connect(lambda *_: self.revisar())
        sb.valueChanged.connect(lambda *_: self.revisar())
        self.hide()

    def revisar(self):
        sb = self.scroll.verticalScrollBar()
        vp = self.scroll.viewport()
        self.setGeometry(vp.x(), vp.y() + vp.height() - 34, vp.width(), 34)
        self.setVisible(sb.maximum() > 0 and sb.value() < sb.maximum() - 2)
        self.raise_()

    def paintEvent(self, e):
        from PySide6.QtGui import QLinearGradient
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, estilo.alfa(estilo.c("fondo"), 0))
        g.setColorAt(1, estilo.alfa(estilo.c("fondo"), 235))
        p.fillRect(self.rect(), g)
        p.end()


class _PanelVista(QFrame):
    """Fondo del lado de la vista previa: una tarjeta con esquinas suaves, con una cuadrícula de puntos.
    Los puntos son un mosaico ya dibujado (uno solo por tema y pantalla): el panel se repinta en cada
    cuadro del zoom animado y así no cuesta nada."""
    MARGEN = (6, 12, 14, 12)   # izquierda, arriba, derecha, abajo: aire para que se vean las esquinas
    RADIO = 12
    PASO = 22                  # separación de los puntos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mosaico = None   # (clave, QPixmap)

    def tarjeta(self):
        i, a, d, b = self.MARGEN
        return QRectF(self.rect()).adjusted(i + 0.5, a + 0.5, -d - 0.5, -b - 0.5)

    def _puntos(self):
        dpr = self.devicePixelRatioF()
        clave = (isDarkTheme(), dpr)
        if not self._mosaico or self._mosaico[0] != clave:
            lado = self.PASO
            pm = QPixmap(round(lado * dpr), round(lado * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            q.setPen(Qt.NoPen)
            q.setBrush(estilo.c("punto"))
            q.drawEllipse(QPointF(lado / 2, lado / 2), 1.1, 1.1)
            q.end()
            self._mosaico = (clave, pm)
        return self._mosaico[1]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for hijo in self.children():   # el velo de «generando» sigue a la tarjeta
            if isinstance(hijo, _Velo) and hijo.isVisible():
                hijo.cubrir()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.tarjeta()
        forma = QPainterPath()
        forma.addRoundedRect(r, self.RADIO, self.RADIO)
        p.fillPath(forma, estilo.c("panel"))
        p.save()
        p.setClipPath(forma)
        p.drawTiledPixmap(r.toAlignedRect(), self._puntos())
        p.restore()
        p.setPen(QPen(estilo.c("borde"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(forma)
        p.end()


class _Lienzo(QWidget):
    """El comprobante flotando sobre el panel, con sombra suave (pintada: no frena la vista en vivo).
    Cada vista nueva entra con un fundido cruzado sobre la anterior; la primera, subiendo suavemente."""

    SEGUIDAS = 0.6   # s: vistas más seguidas que esto (escribiendo) cambian al instante, sin fundido

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None         # la imagen ya escalada al tamaño en pantalla (nítida)
        self.fuente = None     # la imagen original: se usa mientras el zoom está animándose
        self.escalando = False
        self.previo = None
        self._t = 1.0          # 0 → 1: fundido de la imagen anterior a la nueva
        self._entrada = 1.0    # 0 → 1: la primera imagen sube y aparece
        self._ultima = 0.0     # cuándo llegó la imagen anterior

    def escalar(self, ancho, alto):
        """Un cuadro del zoom animado: solo cambia el tamaño en pantalla y dibuja la imagen original
        escalada al vuelo (rápido). Al terminar, poner() deja la imagen nítida de ese tamaño."""
        self.escalando = True
        self.previo = None
        m = MARGEN_LIENZO
        self.resize(round(ancho) + 2 * m, round(alto) + 2 * m)
        self.update()

    def poner(self, pm, fundido=True):
        anterior = self.pm
        self.pm = pm
        self.escalando = False
        ahora = time.monotonic()
        seguidas, self._ultima = ahora - self._ultima < self.SEGUIDAS, ahora
        m = MARGEN_LIENZO
        tam = pm.deviceIndependentSize().toSize()
        mismo_tam = anterior is not None and anterior.deviceIndependentSize().toSize() == tam
        self.resize(tam.width() + 2 * m, tam.height() + 2 * m)
        if anterior is None:
            self.previo = None
            estilo.animar(self, "_ani_e", 0.0, 1.0, 420, self._paso_e, QEasingCurve.OutCubic)
        elif fundido and mismo_tam and anterior.cacheKey() != pm.cacheKey() and not seguidas:
            self.previo = anterior   # un cambio suelto (p. ej. Boda → XV): fundido corto
            estilo.animar(self, "_ani", 0.0, 1.0, 110, self._paso, QEasingCurve.OutQuad)
        else:
            if getattr(self, "_ani", None) is not None:
                self._ani.stop()
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
        if not self.pm and not (self.escalando and self.fuente is not None):
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
        if self.escalando and self.fuente is not None and not self.fuente.isNull():
            p.setRenderHint(QPainter.SmoothPixmapTransform)   # zoom animándose: la original, al vuelo
            p.drawPixmap(r, self.fuente, QRectF(self.fuente.rect()))
        elif self.previo is not None and self._t < 1:
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


def _ease_in(t):
    return t * t * t


def _ease_out(t):
    return 1 - (1 - t) ** 3


def _ease_back(t, s=1.9):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


class _Velo(QWidget):
    """Capa sobre la vista previa, dibujada en vectores (nítida a cualquier tamaño y en ambos temas):
    - «cargando»: la vista se atenúa con un velo suave y una claqueta golpea y suelta un recibo.
    - «listo»: un círculo verde crece con rebote, el ✓ se dibuja y salta confeti; luego se desvanece.
    No tiene caja propia: se funde con el panel."""

    COLORES_CONFETI = ["#E5252A", "#F5C542", "#22C55E", "#FFFFFF", "#FF7A7E", "#3B82F6"]

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.modo = None
        self.titulo = self.sub = ""
        self._opac = 0.0
        self._t = 0.0
        self._confeti = []
        self._reloj = QVariantAnimation(self)
        self._reloj.setStartValue(0.0)
        self._reloj.setEndValue(1.0)
        self._reloj.valueChanged.connect(self._tic)
        self.hide()

    def _tic(self, v):
        self._t = v
        self.update()

    def _poner_opac(self, v):
        self._opac = max(0.0, min(1.0, v))
        self.update()

    def cubrir(self):
        padre = self.parent()
        if padre:   # sobre la tarjeta del panel (con sus esquinas), o todo el padre
            self.setGeometry(padre.tarjeta().toAlignedRect() if hasattr(padre, "tarjeta") else padre.rect())

    def _crear_confeti(self):
        import random
        azar = random.Random(7)
        self._confeti = []
        for i in range(34):
            ang = math.radians(azar.uniform(-160, -20))          # hacia arriba, en abanico
            vel = azar.uniform(170, 330)
            self._confeti.append(dict(
                vx=math.cos(ang) * vel, vy=math.sin(ang) * vel, giro=azar.uniform(-540, 540),
                color=QColor(self.COLORES_CONFETI[i % len(self.COLORES_CONFETI)]),
                w=azar.uniform(4, 8), h=azar.uniform(7, 12), redondo=azar.random() < 0.3,
                retraso=azar.uniform(0, 0.06)))

    def mostrar(self, modo, titulo, sub="", ms_visible=None):
        self.modo, self.titulo, self.sub = modo, titulo, sub
        self.cubrir()
        self.show()
        self.raise_()
        self._reloj.stop()
        if modo == "listo":
            self._crear_confeti()
            self._reloj.setDuration(1500)
            self._reloj.setLoopCount(1)
        else:
            self._reloj.setDuration(1150)
            self._reloj.setLoopCount(-1)
        if estilo.ANIMAR:
            self._reloj.start()
        else:
            self._t = 1.0 if modo == "listo" else 0.5
        estilo.animar(self, "_ani_op", self._opac, 1.0, 240, self._poner_opac)
        if ms_visible:
            QTimer.singleShot(ms_visible, self.ocultar)

    def ocultar(self):
        if not self.isVisible():
            return

        def fin():
            self.hide()
            self._reloj.stop()
        estilo.animar(self, "_ani_op", self._opac, 0.0, 380, self._poner_opac, QEasingCurve.InOutQuad, fin)

    # ---------- dibujo ----------
    def paintEvent(self, e):
        if self._opac <= 0:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        base = estilo.c("panel")
        velo = QColor(base)
        velo.setAlpha(int((150 if self.modo == "cargando" else 110) * self._opac))
        forma = QPainterPath()   # las mismas esquinas suaves de la tarjeta del panel
        forma.addRoundedRect(QRectF(self.rect()), _PanelVista.RADIO, _PanelVista.RADIO)
        p.setClipPath(forma)
        p.fillRect(self.rect(), velo)
        centro = QPointF(self.width() / 2, self.height() / 2 - 26)
        # halo: el centro queda limpio para la animación y el texto, y se funde hacia los bordes (sin caja)
        halo = QRadialGradient(QPointF(centro.x(), centro.y() + 40), 250)
        for pos, a in ((0.0, 250), (0.55, 225), (0.8, 110), (1.0, 0)):
            col = QColor(base)
            col.setAlpha(int(a * self._opac))
            halo.setColorAt(pos, col)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(centro.x(), centro.y() + 40), 250, 250)
        p.setOpacity(self._opac)
        if self.modo == "cargando":
            self._claqueta(p, centro, self._t)
        else:
            self._listo(p, centro, self._t)
        f = QFont(self.font())
        f.setPixelSize(17)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(estilo.c("texto"))
        y = centro.y() + 66
        p.drawText(QRectF(0, y, self.width(), 26), Qt.AlignCenter, self.titulo)
        if self.sub:
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(estilo.c("texto2"))
            p.drawText(QRectF(0, y + 26, self.width(), 20), Qt.AlignCenter, self.sub)
        p.end()

    def _claqueta(self, p, c, t):
        """Claqueta de línea: el brazo con franjas rojas baja de golpe, rebota apenas y vuelve a abrir;
        en cada golpe sale un recibo por debajo y saltan tres rayitas de impacto."""
        S = 92
        tinta, fondo = estilo.c("texto"), estilo.c("sup2")
        cuerpo = QRectF(c.x() - S / 2, c.y() - S * 0.12, S, S * 0.6)
        # recibo que sale por debajo después del golpe
        if t > 0.42:
            k = _ease_out(min(1.0, (t - 0.42) / 0.38))
            alfa_r = 1.0 if t < 0.85 else max(0.0, 1 - (t - 0.85) / 0.15)
            ancho_r, alto_r = S * 0.56, S * 0.36
            r = QRectF(c.x() - ancho_r / 2, cuerpo.bottom() - alto_r + 4 + alto_r * 0.82 * k, ancho_r, alto_r)
            camino = QPainterPath(QPointF(r.left(), r.top()))
            camino.lineTo(r.right(), r.top())
            camino.lineTo(r.right(), r.bottom())
            dientes = 6
            for i in range(dientes, 0, -1):
                x1 = r.left() + r.width() * (i - 0.5) / dientes
                x2 = r.left() + r.width() * (i - 1) / dientes
                camino.lineTo(x1, r.bottom() - 5)
                camino.lineTo(x2, r.bottom())
            camino.closeSubpath()
            p.save()
            p.setOpacity(p.opacity() * alfa_r)
            p.setPen(QPen(tinta, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(estilo.c("sup"))
            p.drawPath(camino)
            p.setPen(QPen(estilo.c("texto3"), 2, Qt.SolidLine, Qt.RoundCap))
            for i, ancho in enumerate((0.6, 0.42)):
                yl = r.top() + r.height() * (0.42 + i * 0.22)
                p.drawLine(QPointF(r.left() + 9, yl), QPointF(r.left() + 9 + (r.width() - 18) * ancho, yl))
            p.restore()
        # cuerpo
        p.setPen(QPen(tinta, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(fondo)
        p.drawRoundedRect(cuerpo, 8, 8)
        p.setPen(QPen(estilo.c("texto3"), 2.2, Qt.SolidLine, Qt.RoundCap))
        for i in (1, 2):
            yl = cuerpo.top() + cuerpo.height() * i / 3
            p.drawLine(QPointF(cuerpo.left() + 12, yl), QPointF(cuerpo.right() - 12, yl))
        # brazo: ángulo -26° (abierto) → 0° (golpe) con aceleración, y vuelve a abrir suave
        if t < 0.42:
            ang = -26 * (1 - _ease_in(t / 0.42))
        elif t < 0.5:
            ang = 2.2 * math.sin((t - 0.42) / 0.08 * math.pi)      # rebote mínimo al chocar
        else:
            ang = -26 * _ease_out((t - 0.5) / 0.5)
        alto_b = S * 0.17
        p.save()
        p.translate(cuerpo.left(), cuerpo.top() - 3)
        p.rotate(ang)
        brazo = QRectF(0, -alto_b, S, alto_b)
        camino = QPainterPath()
        camino.addRoundedRect(brazo, 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(fondo)
        p.drawPath(camino)
        p.setClipPath(camino)
        p.setBrush(QColor(estilo.ROJO))
        paso = S / 6
        for i in range(-1, 7):                                       # franjas diagonales rojas
            x = i * paso
            franja = QPainterPath(QPointF(x, 0))
            franja.lineTo(x + paso * 0.5, 0)
            franja.lineTo(x + paso * 0.5 + alto_b * 0.8, -alto_b)
            franja.lineTo(x + alto_b * 0.8, -alto_b)
            franja.closeSubpath()
            p.drawPath(franja)
        p.setClipping(False)
        p.setPen(QPen(tinta, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(camino)
        p.restore()
        # bisagra
        p.setPen(QPen(tinta, 2.4))
        p.setBrush(fondo)
        p.drawEllipse(QPointF(cuerpo.left() + 2, cuerpo.top() - 3), 4.5, 4.5)
        # rayitas de impacto
        if 0.4 < t < 0.62:
            k = (t - 0.4) / 0.22
            p.setPen(QPen(estilo.alfa(estilo.ROJO, int(255 * (1 - k))), 2.6, Qt.SolidLine, Qt.RoundCap))
            base = QPointF(cuerpo.right() + 6, cuerpo.top() - 8)
            for grados in (-35, 0, 35):
                rad = math.radians(grados)
                ini = base + QPointF(math.cos(rad), math.sin(rad)) * (4 + 8 * k)
                fin = base + QPointF(math.cos(rad), math.sin(rad)) * (12 + 10 * k)
                p.drawLine(ini, fin)

    def _listo(self, p, c, t):
        """Círculo verde que crece con rebote, onda que se expande, ✓ que se dibuja y confeti."""
        R = 38
        k = max(0.0, min(1.0, t / 0.32))
        esc = _ease_back(k) if k < 1 else 1.0
        self._pintar_confeti(p, c, R, t)          # detrás del círculo: sale desde su borde
        # onda
        if 0.18 < t < 0.75:
            q = (t - 0.18) / 0.57
            p.setPen(QPen(estilo.alfa(estilo.VERDE, int(150 * (1 - q))), 3))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, R + 26 * _ease_out(q), R + 26 * _ease_out(q))
        # resplandor y círculo
        p.setPen(Qt.NoPen)
        for i, a in enumerate((38, 22, 10)):
            p.setBrush(estilo.alfa(estilo.VERDE, int(a * esc)))
            p.drawEllipse(c, R * esc + 6 + 6 * i, R * esc + 6 + 6 * i)
        p.setBrush(QColor(estilo.VERDE))
        p.drawEllipse(c, R * esc, R * esc)
        # ✓ que se dibuja
        trazo = max(0.0, min(1.0, (t - 0.26) / 0.3))
        if trazo > 0:
            a = c + QPointF(-R * 0.42, R * 0.02)
            b = c + QPointF(-R * 0.1, R * 0.32)
            d = c + QPointF(R * 0.45, -R * 0.3)
            p.setPen(QPen(QColor("white"), 5.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            if trazo < 0.35:
                p.drawLine(a, a + (b - a) * (trazo / 0.35))
            else:
                p.drawPolyline([a, b, b + (d - b) * _ease_out((trazo - 0.35) / 0.65)])
    def _pintar_confeti(self, p, c, R, t):
        """Confeti con gravedad, giro y desvanecido; cada pieza nace en el borde del círculo."""
        if t > 0.34:
            for q in self._confeti:
                s = max(0.0, (t - 0.34 - q["retraso"]) / 0.66) * 1.15   # segundos simulados
                if s <= 0:
                    continue
                vel = math.hypot(q["vx"], q["vy"]) or 1
                x = c.x() + q["vx"] / vel * R * 0.95 + q["vx"] * s
                y = c.y() + q["vy"] / vel * R * 0.95 + q["vy"] * s + 0.5 * 520 * s * s
                alfa_c = max(0.0, 1 - s ** 1.6)
                if alfa_c <= 0:
                    continue
                col = QColor(q["color"])
                if col.lightness() > 240 and not isDarkTheme():
                    col = estilo.c("texto3")
                col.setAlpha(int(255 * alfa_c))
                p.save()
                p.translate(x, y)
                p.rotate(q["giro"] * s)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                if q["redondo"]:
                    p.drawEllipse(QPointF(0, 0), q["w"] / 2, q["w"] / 2)
                else:
                    p.drawRoundedRect(QRectF(-q["w"] / 2, -q["h"] / 2, q["w"], q["h"]), 1.5, 1.5)
                p.restore()


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
        self.revisando = False      # la ventana revisa las fuentes al abrir: la vista en vivo espera
        self.zoom = 1.0             # zoom de la vista previa (1 = ajustada al panel); el que se ve ahora
        self._zoom_meta = 1.0       # a dónde va (la rueda anima de self.zoom hacia aquí)
        self._zoom_ancla = QPointF()
        self._zoom_prop = (0.5, 0.5)
        self._zoom_calidad = QTimer(self)   # el deslizador: imagen nítida cuando se deja de mover
        self._zoom_calidad.setSingleShot(True)
        self._zoom_calidad.setInterval(120)
        self._zoom_calidad.timeout.connect(self._zoom_listo)
        self._ani_zoom = QVariantAnimation(self)
        self._ani_zoom.setDuration(180)
        self._ani_zoom.setEasingCurve(QEasingCurve.OutCubic)
        self._ani_zoom.valueChanged.connect(self._zoom_visual)
        self._ani_zoom.finished.connect(self._zoom_listo)
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
        self.desvanecido = _Desvanecido(scroll)
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
            # el clic manda «checked» (bool): sin *_ ocuparía el lugar del nombre y el evento quedaba en False
            self.seg.addItem(nombre, nombre, onClick=lambda *_, n=nombre: self._evento(n))
        self.seg.setCurrentItem(self.evento)
        self.seg.setFixedWidth(190)
        self.b1.en_cabecera(self.seg)
        self.festejado = LineEdit()
        self.festejado.setPlaceholderText("Ej. Ana y Luis  /  Sofía Martínez")
        self.festejado.setClearButtonEnabled(True)
        self.lugar = LineEdit()
        self.lugar.setPlaceholderText("Ej. Hotel Camino Real, Guatemala")
        self.lugar.setClearButtonEnabled(True)
        self.fecha_evento = CampoFecha()         # se escribe de corrido; el calendario es opcional
        self.fecha_evento.setDate(QDate.currentDate())
        self.nota_fecha = CaptionLabel("")
        self.telefono = LineEdit()
        self.telefono.setText("+502 ")
        self.telefono.setPlaceholderText("+502 0000 0000")
        for campo in (self.festejado, self.lugar):  # al salir del campo, que se vea desde el inicio
            campo.editingFinished.connect(lambda c=campo: c.setCursorPosition(0))
            # si el texto cambia sin el foco (limpiar, datos cargados), que se vea desde el inicio; completo en el tooltip
            campo.textChanged.connect(lambda txt, c=campo: (c.setToolTip(txt), None if c.hasFocus() else c.setCursorPosition(0)))
        self.telefono.editingFinished.connect(
            lambda: self.telefono.setText(formatear_telefono(self.telefono.text())))
        self.nota_fecha.setWordWrap(False)       # siempre en un renglón (con la letra de Mac se partía)
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
        # Extras solo para este cliente (Cabina 360, zancos, espejo mágico…): van en su lista y suman al total
        self.extras, self.chips_extra = [], []        # [(clave, opción)]
        self.caja_extras = QWidget()
        self.flujo_extras = FlowLayout(self.caja_extras, needAni=False)
        self.flujo_extras.setContentsMargins(0, 0, 0, 0)
        self.flujo_extras.setHorizontalSpacing(8)
        self.flujo_extras.setVerticalSpacing(6)
        self.b_extra = PushButton(FIF.ADD, "Agregar extra")      # en la cabecera: no gasta un renglón
        self.b_extra.setFixedHeight(30)
        self.b_extra.setToolTip("Suma un extra solo para este cliente: aparece en su lista y en el total")
        self.b_extra.installEventFilter(ToolTipFilter(self.b_extra))
        self.b_extra.clicked.connect(self._menu_extras)
        self.b2.en_cabecera(self.b_extra)
        self.caja_extras.hide()                         # la fila de fichas aparece solo si hay extras
        self.b2.cuerpo.addWidget(self.caja_extras)
        v.addWidget(self.b2)

        # ---- ③ Pago y captura ----
        self.b3 = Bloque(3, "Pago y captura", "recibo")
        self.total = Monto()
        self.reserva = Monto()
        self.fecha_pago = CampoFecha()
        self.fecha_pago.setDate(QDate.currentDate())
        self.b3.cuerpo.addWidget(Rejilla([
            _campo("Precio total", self.total), _campo("Reserva / anticipo", self.reserva),
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
        i, a, d, b = _PanelVista.MARGEN     # dentro de la tarjeta, con su propio aire
        p.setContentsMargins(i + 18, a + 12, d + 14, b + 6)
        p.setSpacing(6)
        cabv = QHBoxLayout()
        cabv.setSpacing(10)
        self.b_volver = TransparentPushButton(FIF.LEFT_ARROW, "Datos")     # solo en ventanas angostas
        self.b_volver.clicked.connect(lambda: self._ver_vista(False))
        cabv.addWidget(self.b_volver)
        self.titulo_vista = StrongBodyLabel("Vista previa")   # (si está en vivo lo dice la píldora)
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
        # Zoom: deslizador (100 % = ajustado al panel), − / +, y la rueda del mouse sobre el comprobante
        self.b_menos = TransparentToolButton(FIF.ZOOM_OUT)
        self.b_mas = TransparentToolButton(FIF.ZOOM_IN)
        self.deslizador_zoom = Slider(Qt.Horizontal)
        self.deslizador_zoom.setRange(int(ZOOM_MIN * 100), int(ZOOM_MAX * 100))
        self.deslizador_zoom.setSingleStep(10)
        self.deslizador_zoom.setPageStep(50)
        self.deslizador_zoom.setValue(100)
        self.deslizador_zoom.setFixedWidth(120)
        self.deslizador_zoom.valueChanged.connect(lambda v: self._poner_zoom(v / 100, animar=False))
        self.l_zoom = CaptionLabel("100 %")
        self.l_zoom.setFixedWidth(40)
        self.l_zoom.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for b, paso in ((self.b_menos, -0.25), (self.b_mas, 0.25)):
            b.setFixedSize(28, 28)
            b.clicked.connect(lambda _=False, d=paso: self._poner_zoom(self._zoom_meta + d))
        consejo = "Zoom de la vista previa: rueda del mouse sobre el comprobante, arrastrar para moverse, doble clic para ajustar"
        for w in (self.b_menos, self.deslizador_zoom, self.b_mas, self.l_zoom):
            w.setToolTip(consejo)
            w.installEventFilter(ToolTipFilter(w))
        self.b_ext = TransparentToolButton(FIF.FULL_SCREEN)
        self.b_ext.setToolTip("Abrir en el visor de imágenes")
        self.b_ext.installEventFilter(ToolTipFilter(self.b_ext))
        self.b_ext.clicked.connect(lambda: abrir(self._imagen_actual()))
        cabv.addWidget(self.b_menos)
        cabv.addWidget(self.deslizador_zoom)
        cabv.addWidget(self.b_mas)
        cabv.addWidget(self.l_zoom)
        cabv.addSpacing(4)
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
        self._arrastre = None                  # punto donde empezó a arrastrarse el comprobante ampliado
        for w in (self.lienzo, self.area.viewport()):
            w.installEventFilter(self)
        p.addWidget(self.area, 1)
        cuerpo.addWidget(panel, 56)
        self.velo = _Velo(panel)          # «generando» y «listo» animados sobre la vista previa

        # ================= Barra fija inferior =================
        barra = self.barra = _Barra()
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
        self.btn_copiar.setFixedHeight(40)
        self.btn_copiar.clicked.connect(self.copiar)
        self.btn_wa = PushButton(FIF.CHAT.icon(color=QColor(estilo.VERDE)), "WhatsApp")
        self.btn_wa.setFixedHeight(40)
        self.btn_wa.setToolTip("Abre el chat del cliente; el comprobante queda copiado para pegar")
        self.btn_wa.installEventFilter(ToolTipFilter(self.btn_wa))
        self.btn_wa.clicked.connect(self.whatsapp)
        self.atajo = Atajo(f"{CTRL}Enter")
        self.btn_generar = PrimaryPushButton(FIF.ACCEPT, "Generar comprobante")
        self.btn_generar.setToolTip(f"{CTRL}Enter")
        self.btn_generar.installEventFilter(ToolTipFilter(self.btn_generar))
        self.btn_generar.setFixedHeight(40)
        estilo.boton_principal(self.btn_generar, FIF.ACCEPT)
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
        # Vista en vivo: cada tecla pide la vista de inmediato (el temporizador en 0 solo junta los cambios
        # que llegan a la vez, p. ej. al pegar o limpiar). Si PhotoCraft aún pinta la anterior, la nueva
        # espera su turno con los datos más recientes; el tope evita que una racha de teclas la posponga.
        self.temporizador = QTimer(self)
        self.temporizador.setSingleShot(True)
        self.temporizador.setInterval(0)
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

    def revision_terminada(self):
        """La ventana terminó de revisar (e instalar) las fuentes: sale la vista que esperaba, o se deja
        PhotoCraft listo para la primera tecla."""
        self.revisando = False
        if self.vista_pendiente and not self.vista_ocupada:
            self._render_vista()
        else:
            self._calentar_vista()

    def _calentar_vista(self):
        """PhotoCraft listo antes de la primera tecla (al terminar de revisar las fuentes)."""
        if self.en_vivo.isChecked() and not self.vista_ocupada and self.vista_ruta is None:
            # hilo de Python (daemon) y no QThread: si se cierra el programa mientras tanto, no lo traba
            threading.Thread(target=motor.calentar_vista, daemon=True,
                             args=(self._datos(para_vista=True), self.cfg, self._lado_vista())).start()

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
        self.servicios.poner(self._servicios())
        self.total.setValue(int(paq["precio"] + self._total_extras()))
        if desde_usuario:
            self._cambio()
            if not self.en_vivo.isChecked() and not (self.ultimo and not self.sin_generar):
                self._mostrar_plantilla()      # sin vista en vivo: al menos la plantilla del paquete elegido

    # ---- Extras (solo para este cliente) ----
    def _catalogo_extras(self):
        return {e["clave"]: e for e in self.cfg.get("extras", [])}

    def _items_extras(self):
        ex = self._catalogo_extras()
        return [motor.item_extra(ex[c], o) for c, o in self.extras if c in ex]

    def _total_extras(self):
        ex = self._catalogo_extras()
        return sum(motor.precio_extra(ex[c], o) for c, o in self.extras if c in ex)

    def _servicios(self):
        """Lo que dice el comprobante: el paquete (con sus cambios de la página Paquetes) y los extras."""
        return motor.con_extras(self.cfg["paquetes"][self.paquete].get("incluye", []), self._items_extras())

    def _mostrar_extras(self):
        """Fichas de los extras en su fila; con la ventana baja (formulario apretado) la fila no se ve y el
        botón dice cuántos hay (se quitan desde su menú)."""
        n = len(self.chips_extra)
        self.caja_extras.setVisible(bool(n) and not getattr(self, "apretado", False))
        self.b_extra.setText(f"Extras ({n})" if n and getattr(self, "apretado", False) else "Agregar extra")

    def _menu_extras(self):
        menu = RoundMenu(parent=self)
        ex = self._catalogo_extras()
        for i, (c, o) in enumerate(self.extras):     # los ya agregados, para quitarlos desde aquí también
            if c in ex:
                a = Action(FIF.DELETE, f"Quitar {ex[c]['titulo']} · {ex[c]['opciones'][o][0]}", self)
                a.triggered.connect(lambda _=False, i=i: self._quitar_extra(i))
                menu.addAction(a)
        if self.extras:
            menu.addSeparator()
        for extra in self.cfg.get("extras", []):
            sub = RoundMenu(extra["titulo"], self)
            sub.setIcon(estilo.icono(extra["icono"]))
            for i, (texto, precio) in enumerate(extra["opciones"]):
                a = Action(f"{texto}  ·  {q(precio)}", self)
                a.triggered.connect(lambda _=False, c=extra["clave"], o=i: self._agregar_extra(c, o))
                sub.addAction(a)
            menu.addMenu(sub)
        menu.exec(self.b_extra.mapToGlobal(QPoint(0, self.b_extra.height() + 4)))

    def _agregar_extra(self, clave, opcion):
        if len(self._servicios()) >= MAX_SERVICIOS:
            aviso(self, "warning", "Demasiados servicios",
                  f"El comprobante admite hasta {MAX_SERVICIOS} servicios para que se lean bien en el teléfono.")
            return
        self.extras.append((clave, opcion))
        self._poner_extras()

    def _quitar_extra(self, i):
        if 0 <= i < len(self.extras):
            del self.extras[i]
        self._poner_extras()

    def _poner_extras(self, avisar=True):
        for w in self.chips_extra:
            self.flujo_extras.removeWidget(w)
            w.deleteLater()
        ex = self._catalogo_extras()
        self.chips_extra = []
        for i, (c, o) in enumerate(self.extras):
            e = ex.get(c)
            if not e:
                continue
            texto, precio = e["opciones"][o]
            chip = _ChipExtra(f"{e['titulo']} · {texto} · {q(precio)}", e["icono"])
            chip.quitar.connect(lambda i=i: self._quitar_extra(i))
            self.flujo_extras.insertWidget(len(self.chips_extra), chip)
            self.chips_extra.append(chip)
        self._mostrar_extras()
        if avisar:
            self.elegir_paquete(self.paquete)    # lista y total con los extras

    def actualizar_precios(self):
        for clave, t in self.tarjetas.items():
            t.actualizar_precio(self.cfg["paquetes"][clave]["precio"])
        self.elegir_paquete(self.paquete)

    def _estado_bloques(self):
        fe = self.fecha_evento.getDate().toPython()
        self.nota_fecha.setText(f"{fecha_larga(fe).split(' ')[0][:3]} · {faltan(fe)}")
        self.nota_fecha.setToolTip(fecha_larga(fe).capitalize())
        f1 = [n for n, ok in (("festejado", self.festejado.text().strip()),
                              ("lugar", self.lugar.text().strip()),
                              ("teléfono", len(digitos_telefono(self.telefono.text())) >= 10)) if not ok]
        self.b1.poner_estado(not f1, " · ".join(x for x in (
            self.festejado.text().strip() or "Sin nombre", self.lugar.text().strip(),
            fe.strftime("%d/%m/%Y"), self.telefono.text().strip(), self.evento) if x),
            falta=f1[0] if len(f1) == 1 else (f"{len(f1)} datos" if f1 else None))
        n_extras = len(self._items_extras())
        self.b2.poner_estado(True, f"{NOMBRES_PAQUETE.get(self.paquete, self.paquete)} · {q(self.total.value())} · "
                                   f"{len(self._servicios())} servicios"
                                   + (f" · {n_extras} extra{'s' if n_extras != 1 else ''}" if n_extras else ""))
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
            total=total, monto=monto, saldo=max(total - monto, 0), servicios=self._servicios(),
            concepto="RESERVA CON" if monto < total else "PAGO FINAL", captura=self.zona.ruta)

    def _render_vista(self):
        self.temporizador.stop()
        self.tope_vista.stop()
        if not self.en_vivo.isChecked():
            return
        # Bandera propia y no isRunning(): «listo» llega cuando el hilo aún no termina run(), y con
        # isRunning() la vista siguiente quedaba en espera sin que nadie la lanzara (vista congelada).
        # Mientras se revisan las fuentes (al abrir) también espera: la lanza revision_terminada().
        if self.vista_ocupada or self.revisando:
            if self.revisando and self.vista_ruta is None:
                self.estado.setText("Preparando la vista previa…")
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
        self.titulo_vista.setText("Vista previa")
        texto =(("Hay cambios sin generar · " if self.sin_generar else "") +
                 "Así quedará · se actualiza mientras escribes")
        if self.estado.text() != texto:
            self.estado.setText(texto)
        hilo = self.vista_trabajo   # una vista a la vez: es el que acaba de avisar
        propia = hilo is not None and Path(ruta).stem == Path(str(hilo.destino)).stem
        self._poner_imagen(ruta, hilo.imagen if propia else None)
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
        vista = rutas.recurso("PLANTILLAS/VISTA PREVIA.jpg")    # una sola plantilla; la lista va al generar
        self.estado.setText("Plantilla del comprobante · se actualizará con tus datos")
        if Path(vista).exists():
            self._poner_imagen(vista)

    def _imagen_actual(self):
        if self.ultimo and not self.sin_generar:
            return self.ultimo
        return self.vista_ruta

    def _poner_imagen(self, ruta, imagen=None):
        # QImage y no QPixmap(ruta): QPixmap guarda en caché por nombre y hora (en segundos) y,
        # con la vista en vivo rápida, podía mostrar la imagen anterior del mismo archivo.
        # imagen: la vista en vivo ya leída en su hilo (así la ventana no se traba al recibirla).
        self.pix = QPixmap.fromImage(imagen if imagen is not None and not imagen.isNull() else QImage(str(ruta)))
        self.lienzo.fuente = self.pix
        self._ajustar_imagen()

    def _tam_ajustado(self):
        """Ancho y alto (px lógicos) del comprobante ajustado al panel: el 100 % del zoom."""
        vp = self.area.viewport().size()
        m = 2 * MARGEN_LIENZO
        prop = 3508 / 2480   # la plantilla es A4 vertical
        ancho = min(max(vp.width() - m, 60), max(vp.height() - m, 60) / prop)
        return ancho, ancho * prop

    def _lado_vista(self):
        """Lado mayor (en píxeles reales) que necesita la vista para verse nítida en este panel con el zoom
        actual: PhotoCraft la pinta de ese tamaño y no más grande (así tarda menos)."""
        _, alto = self._tam_ajustado()
        alto = max(alto, 400) * self.zoom
        return int(max(600, min(alto * self.devicePixelRatioF(), motor.SesionPhotoCraft.LADO_MAX)))

    def _zoom_animandose(self):
        return self._ani_zoom.state() == QAbstractAnimation.Running

    def _ajustar_imagen(self):
        if not getattr(self, "pix", None) or self.pix.isNull() or not self.panel_vista.isVisible():
            return
        if self._zoom_animandose():   # a mitad del zoom: se dibuja la original; la nítida va al final
            self.lienzo.update()
            return
        dpr = self.devicePixelRatioF()          # pantallas Retina / 4K: la imagen se escala a sus píxeles reales
        ancho, alto = self._tam_ajustado()
        w, h = int(ancho * self.zoom * dpr), int(alto * self.zoom * dpr)
        self.lienzo.fuente = self.pix
        if self.zoom > 1.001 and self.pix.height() < h - 1:
            # ampliada más que la imagen: se dibuja al vuelo (igual de nítida que escalarla antes, sin la
            # pausa ni una copia enorme en memoria); PhotoCraft manda luego una más grande
            self.lienzo.escalar(w / dpr, h / dpr)
        else:
            if abs(self.pix.height() - h) <= 1 and abs(self.pix.width() - w) <= 2:
                img = QPixmap(self.pix)   # la vista en vivo ya viene del tamaño justo: escalarla solo la suaviza
            else:   # más chica que la imagen: se reduce con calidad (al vuelo se vería granulada)
                img = self.pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img.setDevicePixelRatio(dpr)
            self.lienzo.poner(img, fundido=not self.lienzo.escalando)   # tras el zoom: sin fundido
        self.lienzo.setCursor(Qt.OpenHandCursor if self.zoom > 1.001 else Qt.ArrowCursor)
        if self.velo.isVisible():
            self.velo.cubrir()
        if (self.en_vivo.isChecked() and self.vista_ruta and self._imagen_actual() == self.vista_ruta
                and max(self.pix.width(), self.pix.height()) + 48 < self._lado_vista()):
            self.temporizador.start()   # la ventana creció o hay zoom: pedir la vista más nítida

    def _poner_zoom(self, factor, ancla=None, animar=True):
        """Cambia el zoom (1 = ajustado al panel) manteniendo quieto el punto bajo el mouse (ancla, en
        coordenadas del visor) o el centro de lo que se ve. Animado y suave (rueda, botones, doble clic):
        si llega otro cambio a mitad de camino, sigue desde donde va. El deslizador va directo."""
        meta = round(min(ZOOM_MAX, max(ZOOM_MIN, factor)), 3)
        if abs(meta - self._zoom_meta) < 0.001 and abs(meta - self.zoom) < 0.001:
            return
        self._zoom_meta = meta
        vp = self.area.viewport()
        ancla = QPointF(ancla) if ancla is not None else QPointF(vp.width() / 2, vp.height() / 2)
        # el punto bajo el mouse, en proporción de la imagen (la posición del lienzo ya incluye el desplazamiento)
        m = MARGEN_LIENZO
        iw, ih = max(self.lienzo.width() - 2 * m, 1), max(self.lienzo.height() - 2 * m, 1)
        self._zoom_ancla = ancla
        self._zoom_prop = ((ancla.x() - self.lienzo.x() - m) / iw, (ancla.y() - self.lienzo.y() - m) / ih)
        self._zoom_calidad.stop()
        hay_imagen = getattr(self, "pix", None) is not None and not self.pix.isNull()
        self._ani_zoom.stop()
        if animar and hay_imagen and estilo.ANIMAR:   # una sola animación, reapuntada (la rueda manda muchas)
            self._ani_zoom.setStartValue(float(self.zoom))
            self._ani_zoom.setEndValue(float(meta))
            self._ani_zoom.start()
        else:
            self._zoom_visual(meta)
            self._zoom_calidad.start()

    def _zoom_visual(self, z):
        """Un cuadro del zoom: tamaño nuevo y el mismo punto bajo el mouse (barato: sin reescalar)."""
        self.zoom = z
        self.deslizador_zoom.blockSignals(True)
        self.deslizador_zoom.setValue(int(round(z * 100)))
        self.deslizador_zoom.blockSignals(False)
        self.l_zoom.setText(f"{int(round(z * 100))} %")
        if getattr(self, "pix", None) is None or self.pix.isNull():
            return
        ancho, alto = self._tam_ajustado()
        self.lienzo.escalar(ancho * z, alto * z)   # el área ajusta sus barras al instante (sin processEvents)
        m = MARGEN_LIENZO
        (px, py), a = self._zoom_prop, self._zoom_ancla
        self.area.horizontalScrollBar().setValue(round(px * (self.lienzo.width() - 2 * m) + m - a.x()))
        self.area.verticalScrollBar().setValue(round(py * (self.lienzo.height() - 2 * m) + m - a.y()))

    def _zoom_listo(self):
        """El zoom llegó (o el deslizador se soltó): la imagen nítida de ese tamaño y, si hace falta, una
        vista más grande de PhotoCraft."""
        if self._zoom_animandose():
            return
        self.zoom = self._zoom_meta
        h, v = self.area.horizontalScrollBar().value(), self.area.verticalScrollBar().value()
        self._ajustar_imagen()
        self.area.horizontalScrollBar().setValue(h)   # misma posición (el tamaño cambia a lo más 1 px)
        self.area.verticalScrollBar().setValue(v)

    def _alternar_zoom(self, ancla=None):
        """Doble clic (en el punto del clic) o la prueba de la vista en vivo: ajustado ↔ 200 %."""
        self._poner_zoom(1.0 if self._zoom_meta > 1.001 else 2.0, ancla)

    def eventFilter(self, obj, e):
        if obj in (self.lienzo, self.area.viewport()):
            t = e.type()
            if t == QEvent.Wheel and getattr(self, "pix", None):      # rueda: zoom hacia el puntero
                pasos = e.angleDelta().y() / 120   # touchpad: fracciones pequeñas, igual de suave
                if pasos:
                    ancla = self.area.viewport().mapFrom(obj, e.position().toPoint()) if obj is self.lienzo \
                        else e.position().toPoint()
                    self._poner_zoom(self._zoom_meta * (1.2 ** pasos), QPointF(ancla))
                return True
            if t == QEvent.MouseButtonDblClick and e.button() == Qt.LeftButton:
                ancla = self.area.viewport().mapFrom(obj, e.position().toPoint()) if obj is self.lienzo \
                    else e.position().toPoint()
                self._alternar_zoom(QPointF(ancla))
                return True
            if t == QEvent.MouseButtonPress and e.button() == Qt.LeftButton and self.zoom > 1.001:
                self._arrastre = (e.globalPosition(), self.area.horizontalScrollBar().value(),
                                  self.area.verticalScrollBar().value())
                self.lienzo.setCursor(Qt.ClosedHandCursor)
                return True
            if t == QEvent.MouseMove and self._arrastre:
                inicio, hx, vy = self._arrastre
                d = e.globalPosition() - inicio
                self.area.horizontalScrollBar().setValue(int(hx - d.x()))
                self.area.verticalScrollBar().setValue(int(vy - d.y()))
                return True
            if t == QEvent.MouseButtonRelease and self._arrastre:
                self._arrastre = None
                self.lienzo.setCursor(Qt.OpenHandCursor)
                return True
        return super().eventFilter(obj, e)

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
        self._mostrar_extras()
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

    def _ancho_util_vista(self):
        """Ancho del panel en el que el comprobante (A4 vertical) llena el alto disponible al 100 %; nunca
        menos de lo que pide su cabecera (título, «En vivo» y zoom)."""
        alto = self.height() - self.barra.sizeHint().height()
        i, a, d, b = _PanelVista.MARGEN
        vertical = (a + 12) + 40 + 6 + 20 + 6 + 2 * MARGEN_LIENZO + (b + 6)    # márgenes, cabecera y estado
        horizontal = (i + 18) + (d + 14) + 2 * MARGEN_LIENZO + 12
        minimo = self.panel_vista.layout().minimumSize().width() + 8   # lo que pide la cabecera con esta letra
        return int(max(minimo, (alto - vertical) / (3508 / 2480) + horizontal))

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
        # La vista previa no necesita más ancho que el que usa el comprobante a esta altura (es A4 vertical):
        # lo que sobra va al formulario, que así no se apila ni se corta (laptops, ventanas bajas).
        self.panel_vista.setMaximumWidth(16777215 if compacto else self._ancho_util_vista())
        QTimer.singleShot(40, self._revisar_alto)
        QTimer.singleShot(90, self.desvanecido.revisar)
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
        espera = "" if activo else "Primero genera el comprobante"
        self.btn_copiar.setToolTip(espera or "Copiar el comprobante para pegarlo")
        self.btn_wa.setToolTip(espera or "Abre el chat del cliente; el comprobante queda copiado para pegar")

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
        self.extras = []
        self._poner_extras(avisar=False)
        self.elegir_paquete(self.paquete, desde_usuario=False)
        self.abrir_bloque(self.b1)
        self._estado_bloques()
        self._mostrar_plantilla()
        self.titulo_vista.setText("Vista previa")
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
        self.velo.mostrar("cargando", "Creando el comprobante…", "PhotoCraft está armando el JPG")
        self.trabajo = Trabajo(self.datos, self.cfg)
        self.trabajo.listo.connect(self._listo)
        self.trabajo.fallo.connect(self._fallo)
        self.trabajo.start()

    def _fin(self):
        self.btn_generar.setEnabled(True)
        self.ring.hide()
        self.velo.ocultar()        # (si salió bien, _listo lo vuelve a mostrar en modo «listo»)
        self._acomodar()

    def _listo(self, ruta):
        self._fin()
        d = self.datos
        concepto = motor.CONCEPTOS.get(d["concepto"], d["concepto"]).title()
        corregido = self.cliente_id is not None
        if corregido:
            registro.corregir_reserva(self.cliente_id, d["festejado"], d["contacto"], d["evento"], d["paquete"],
                                      d["lugar"], d["fecha_evento"], d["total"], d["fecha_comprobante"],
                                      d["monto"], concepto, ruta, servicios=d.get("servicios"))
        else:
            self.cliente_id = registro.nuevo_cliente(d["festejado"], d["contacto"], d["evento"], d["paquete"],
                                                     d["lugar"], d["fecha_evento"], d["total"],
                                                     servicios=d.get("servicios"))
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
        self.velo.mostrar("listo", "¡Comprobante corregido!" if corregido else "¡Comprobante listo!",
                                 f"Guardado y copiado · pégalo en WhatsApp con {CTRL}V", 2600)
        aviso(self, "success", "Comprobante corregido" if corregido else "Comprobante listo",
              f"Guardado y copiado: pégalo en WhatsApp con {CTRL}V.", 7000, ruta_abrir=ruta)
        abrir_carpeta_si_toca(self.cfg, ruta)

    def _fallo(self, msg):
        self._fin()
        self.estado.setText("No se pudo generar.")
        aviso(self, "error", "Error", msg, 10000)
