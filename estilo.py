"""Sistema de diseño (2026): colores, superficies, píldoras, montos e íconos comunes a todas las pantallas.
Modo oscuro grafito y modo claro; el rojo de la marca solo en acciones principales y estados activos.
Todo se pinta en paintEvent leyendo el tema actual, así cambia al instante con Oscuro/Claro."""
from pathlib import Path

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QWidget
from qfluentwidgets import FluentIcon as FIF, isDarkTheme, qconfig

import rutas

ROJO = "#E5252A"
ROJO_CLARO = "#FF4D52"
VERDE = "#22C55E"
AMBAR = "#F59E0B"
AZUL = "#3B82F6"
RADIO = 14

_OSCURO = dict(fondo="#0F0F12", panel="#131317", sup="#17171C", sup2="#1E1E24", sup3="#26262D",
               borde=(255, 255, 255, 16), borde2=(255, 255, 255, 30), texto="#F2F2F4", texto2="#A1A1AA",
               texto3="#8B8B94", punto=(255, 255, 255, 14))
_CLARO = dict(fondo="#F5F5F7", panel="#EEEEF1", sup="#FFFFFF", sup2="#F8F8FA", sup3="#EFEFF3",
              borde=(0, 0, 0, 20), borde2=(0, 0, 0, 34), texto="#111114", texto2="#52525B",
              texto3="#6B6B74", punto=(0, 0, 0, 18))


def c(nombre):
    """Color del tema actual (fondo, panel, sup, sup2, sup3, borde, borde2, texto, texto2, texto3, punto)."""
    v = (_OSCURO if isDarkTheme() else _CLARO)[nombre]
    return QColor(*v) if isinstance(v, tuple) else QColor(v)


def alfa(color, a):
    col = QColor(color)
    col.setAlpha(a)
    return col


def tinta(color):
    """Color de un texto de estado (verde, ámbar, azul…): en el tema claro, más oscuro para que se lea
    (contraste ≥ 4.5:1 sobre blanco); en el oscuro, tal cual."""
    col = QColor(color)
    return col if isDarkTheme() else col.darker(185)


def boton_principal(boton, icono_fif=None):
    """El botón principal igual en los dos temas: rojo de la marca con texto e ícono blancos
    (Fluent-Widgets lo pinta rosado con texto negro en el tema oscuro)."""
    from qfluentwidgets import setCustomStyleSheet
    qss = (f"PrimaryPushButton{{color:white;background-color:{ROJO};border:1px solid {ROJO};"
           "border-bottom:1px solid #B91C21;}"
           "PrimaryPushButton:hover{background-color:#EC3A3F;border:1px solid #EC3A3F;}"
           "PrimaryPushButton:pressed{background-color:#C41E23;border:1px solid #C41E23;color:rgba(255,255,255,0.85);}"
           "PrimaryPushButton:disabled{background-color:rgba(229,37,42,0.38);border:1px solid rgba(229,37,42,0.0);"
           "color:rgba(255,255,255,0.7);}")
    setCustomStyleSheet(boton, qss, qss)
    if icono_fif is not None:
        boton.setIcon(icono_fif.icon(color=QColor("white")))
    return boton


def mezclar(a, b, t):
    """Color intermedio entre a y b (t de 0 a 1), incluida la transparencia."""
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))


# ================= Movimiento =================
# Animaciones cortas (150-400 ms) con salida suave: dan vida sin hacer esperar. Se pueden apagar en Ajustes.
ANIMAR = True


def animar(dueno, nombre, inicio, fin, ms, al_cambiar, curva=QEasingCurve.OutCubic, al_terminar=None):
    """Anima un número de inicio a fin y llama al_cambiar(valor) en cada cuadro. Guarda la animación en
    dueno.<nombre> (una nueva reemplaza a la anterior). Sin animaciones, salta directo al final."""
    previa = getattr(dueno, nombre, None)
    if previa is not None:
        previa.stop()
    if not ANIMAR or ms <= 0:
        al_cambiar(fin)
        if al_terminar:
            al_terminar()
        return None
    ani = QVariantAnimation(dueno)
    ani.setStartValue(float(inicio))
    ani.setEndValue(float(fin))
    ani.setDuration(ms)
    ani.setEasingCurve(curva)
    ani.valueChanged.connect(al_cambiar)
    if al_terminar:
        ani.finished.connect(al_terminar)
    setattr(dueno, nombre, ani)
    ani.start()
    return ani


def salto(t):
    """Pequeño «pop»: 0 → sube a ~1.08 → 1 (para marcar un cambio de estado)."""
    return 1 + 0.08 * math.sin(math.pi * max(0.0, min(1.0, t)))


def fuente_numeros(px, peso=QFont.DemiBold, base=None):
    """Letra para montos: cifras tabulares (todas del mismo ancho) y peso fuerte."""
    f = QFont(base) if base else QFont()
    f.setPixelSize(px)
    f.setWeight(peso)
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):
        pass
    return f


# ================= Íconos =================
# Íconos de línea blancos (recursos/iconos/*.png, hechos con Higgsfield); se tiñen al color que haga falta.
_CARPETA_ICONOS = "recursos/iconos"
_cache_iconos = {}
RESPALDO = {"camara": FIF.CAMERA, "video": FIF.VIDEO, "corona": FIF.CERTIFICATE, "diamante": FIF.CERTIFICATE,
            "recibo": FIF.DOCUMENT, "calendario": FIF.CALENDAR, "carpeta": FIF.FOLDER, "personas": FIF.PEOPLE,
            "ajustes": FIF.SETTING, "album": FIF.ALBUM, "galeria": FIF.PHOTO, "usb": FIF.SAVE,
            "video_largo": FIF.MOVIE, "video_fotos": FIF.MOVIE, "dron": FIF.AIRPLANE, "buzon": FIF.MICROPHONE,
            "enmarcada": FIF.PHOTO, "cabina360": FIF.SYNC, "chispa": FIF.BRIGHTNESS, "cobertura": FIF.HEART}


def pixmap_icono(nombre, color, tam=20, dpr=2.0):
    """El ícono de línea teñido de un color, del tamaño pedido (en px lógicos)."""
    clave = (nombre, QColor(color).name(QColor.HexArgb), tam, dpr)
    if clave in _cache_iconos:
        return _cache_iconos[clave]
    archivo = Path(rutas.recurso(f"{_CARPETA_ICONOS}/{nombre}.png"))
    lado = int(tam * dpr)
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    if archivo.exists():
        base = QPixmap(str(archivo)).scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p = QPainter(pm)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap((lado - base.width()) // 2, (lado - base.height()) // 2, base)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(pm.rect(), QColor(color))
        p.end()
    else:
        respaldo = RESPALDO.get(nombre, FIF.INFO)
        p = QPainter(pm)
        respaldo.render(p, QRectF(0, 0, lado, lado), fill=QColor(color).name())
        p.end()
    pm.setDevicePixelRatio(dpr)
    _cache_iconos[clave] = pm
    return pm


def icono(nombre, color=None, tam=20):
    """QIcon de línea para botones (color por defecto: el del texto del tema)."""
    return QIcon(pixmap_icono(nombre, color or c("texto"), tam))


class Icono(QWidget):
    """Ícono de línea pintado (cambia de color con el tema si no se fija uno)."""

    def __init__(self, nombre, tam=18, color=None, fondo=None, caja=None, parent=None):
        super().__init__(parent)
        self.nombre, self.tam, self.color, self.fondo = nombre, tam, color, fondo
        lado = caja or tam
        self.setFixedSize(lado, lado)

    def poner(self, nombre=None, color=None):
        if nombre:
            self.nombre = nombre
        if color:
            self.color = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.fondo:
            p.setPen(Qt.NoPen)
            p.setBrush(alfa(self.fondo, 38))
            p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        pm = pixmap_icono(self.nombre, self.color or c("texto2"), self.tam, self.devicePixelRatioF() or 2)
        x = (self.width() - self.tam) / 2
        y = (self.height() - self.tam) / 2
        p.drawPixmap(QPointF(x, y), pm)
        p.end()


# ================= Superficies =================
class Tarjeta(QFrame):
    """Superficie redondeada con borde fino. Opcional: franja de color arriba (acento), anillo de
    selección rojo, y clic (cursor de mano + señal clicked). Al pasar el mouse se ilumina y el anillo
    de selección aparece con un fundido suave (animados)."""
    clicked = Signal()

    def __init__(self, parent=None, acento=None, clicable=False, nivel=1, radio=RADIO):
        super().__init__(parent)
        self.acento = QColor(acento) if acento else None
        self.seleccionada = False
        self.resaltada = False      # p. ej. el paquete más vendido: borde del color de acento
        self.clicable = clicable
        self.nivel = nivel          # 1 = superficie, 2 = un poco más clara
        self.radio = radio
        self._encima = False
        self._t_encima = 0.0        # 0 → 1 al pasar el mouse
        self._t_sel = 0.0           # 0 → 1 al quedar elegida
        self._t_res = 0.0           # 0 → 1 al resaltarse
        self.setAttribute(Qt.WA_StyledBackground, False)
        if clicable:
            self.setCursor(Qt.PointingHandCursor)

    def _poner_t(self, campo, v):
        setattr(self, campo, v)
        self.update()

    def marcar(self, si):
        if si == self.seleccionada and self._t_sel in (0.0, 1.0):
            return
        self.seleccionada = si
        animar(self, "_ani_sel", self._t_sel, 1.0 if si else 0.0, 260 if si else 180,
               lambda v: self._poner_t("_t_sel", v))

    def resaltar(self, si):
        if si == self.resaltada:
            return
        self.resaltada = si
        animar(self, "_ani_res", self._t_res, 1.0 if si else 0.0, 240, lambda v: self._poner_t("_t_res", v))

    def enterEvent(self, e):
        self._encima = True
        if self.clicable:
            animar(self, "_ani_encima", self._t_encima, 1.0, 140, lambda v: self._poner_t("_t_encima", v))
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._encima = False
        if self.clicable:
            animar(self, "_ani_encima", self._t_encima, 0.0, 220, lambda v: self._poner_t("_t_encima", v))
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self.clicable and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        base = c("sup2" if self.nivel == 2 else "sup")
        claro = c("sup3" if self.nivel == 2 else "sup2")
        # (si se fijó .resaltada directamente, sin animar, se dibuja tal cual)
        t_res = self._t_res if hasattr(self, "_ani_res") else (1.0 if self.resaltada else 0.0)
        fondo = mezclar(base, claro, self._t_encima * (1 - self._t_sel))
        if self._t_sel > 0:
            p.setPen(Qt.NoPen)
            for i, a in enumerate((10, 6, 3)):          # brillo suave alrededor
                p.setBrush(alfa(ROJO, int(a * self._t_sel)))
                p.drawRoundedRect(r.adjusted(-2 - 2 * i, -2 - 2 * i, 2 + 2 * i, 2 + 2 * i),
                                  self.radio + 2 + 2 * i, self.radio + 2 + 2 * i)
        p.setPen(QPen(mezclar(c("borde"), c("borde2"), self._t_encima), 1))
        p.setBrush(fondo)
        p.drawRoundedRect(r, self.radio, self.radio)
        if self.acento:
            camino = QPainterPath()
            camino.addRoundedRect(r, self.radio, self.radio)
            p.setClipPath(camino)
            p.setPen(Qt.NoPen)
            p.setBrush(self.acento)
            p.drawRect(QRectF(r.left(), r.top(), r.width(), 3))
            p.setClipping(False)
        anillo = max(self._t_sel, t_res)
        if anillo > 0:
            color = QColor(ROJO) if self._t_sel >= t_res else alfa(self.acento or QColor(ROJO), 150)
            p.setPen(QPen(alfa(color, int(color.alpha() * anillo)), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, -0.6), self.radio, self.radio)
        p.end()


class Pildora(QWidget):
    """Etiqueta redondeada pintada (estado, conteo, sello). Fondo = color con transparencia.
    Al cambiar de color (p. ej. «Falta…» → «Listo») hace un pequeño salto y funde los colores."""

    def __init__(self, texto, color=None, solida=False, icono_nombre=None, tam_letra=12, alto=24, parent=None):
        super().__init__(parent)
        self.texto, self.color, self.solida, self.icono_nombre = texto, color, solida, icono_nombre
        self.tam_letra, self.alto = tam_letra, alto
        self._color_previo = None
        self._t = 1.0
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._medir()

    def _color_actual(self, color):
        return QColor(color) if color else c("texto2")

    def poner(self, texto=None, color=None):
        """Cambia el texto y el color (None = gris neutro)."""
        cambia_color = color != self.color
        if cambia_color:
            self._color_previo = self._color_actual(self.color)
            self.color = color
        if texto is not None:
            self.texto = texto
        self._medir()
        if cambia_color and self.isVisible():
            animar(self, "_ani", 0.0, 1.0, 320, self._paso)
        else:
            self._t = 1.0
            self.update()

    def _paso(self, v):
        self._t = v
        self.update()

    def _fuente(self):
        f = QFont(self.font())
        f.setPixelSize(self.tam_letra)
        f.setWeight(QFont.DemiBold)
        return f

    def _medir(self):
        from PySide6.QtGui import QFontMetrics
        ancho = QFontMetrics(self._fuente()).horizontalAdvance(self.texto) + 20
        if self.icono_nombre:
            ancho += self.tam_letra + 5
        self.setFixedSize(ancho, self.alto)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = self._color_actual(self.color)
        if self._t < 1.0 and self._color_previo is not None:
            color = mezclar(self._color_previo, color, self._t)
            esc = salto(self._t)
            p.translate(self.width() / 2, self.height() / 2)
            p.scale(esc, esc)
            p.translate(-self.width() / 2, -self.height() / 2)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.solida:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            texto = QColor("white")
        else:
            p.setPen(QPen(alfa(color, 70 if isDarkTheme() else 90), 1))
            p.setBrush(alfa(color, 34 if isDarkTheme() else 30))
            texto = tinta(color) if self.color else c("texto2")
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        x = 10
        if self.icono_nombre:
            lado = self.tam_letra + 1
            p.drawPixmap(QPointF(x, (self.alto - lado) / 2), pixmap_icono(self.icono_nombre, texto, lado))
            x += lado + 5
        p.setFont(self._fuente())
        p.setPen(texto)
        p.drawText(QRectF(x, 0, self.width() - x - 8, self.alto), Qt.AlignVCenter | Qt.AlignLeft, self.texto)
        p.end()


class Cifra(QLabel):
    """Monto grande con cifras tabulares (p. ej. el saldo pendiente). Con poner_numero() cuenta del
    valor anterior al nuevo en un instante, como un marcador."""

    def __init__(self, texto="Q0", px=30, color=None, parent=None):
        super().__init__(texto, parent)
        self.px, self.color = px, color
        self.valor = None
        self.formato = str
        self.setFont(fuente_numeros(px, QFont.Bold))
        self._pintar_color()
        qconfig.themeChanged.connect(self._pintar_color)

    def _pintar_color(self, *_):
        col = QColor(self.color) if self.color else c("texto")
        self.setStyleSheet(f"color:{col.name()};background:transparent;")

    def poner_color(self, color):
        if color != self.color:
            self.color = color
            self._pintar_color()

    def poner_numero(self, valor, formato=str, ms=380):
        """Muestra formato(valor) contando desde el número anterior (si no estaba visible, sin contar)."""
        self.formato = formato
        anterior = self.valor
        self.valor = valor
        if anterior is None or anterior == valor or not self.isVisible():
            self.setText(formato(valor))
            return
        entero = isinstance(valor, int) and isinstance(anterior, int)
        animar(self, "_ani", anterior, valor, ms,
               lambda v: self.setText(formato(int(round(v)) if entero else v)))


class Separador(QWidget):
    def __init__(self, vertical=False, parent=None):
        super().__init__(parent)
        self.vertical = vertical
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), c("borde"))
        p.end()


class Atajo(QLabel):
    """Tecla de atajo (p. ej. «Ctrl+Enter») en una cajita discreta."""

    def __init__(self, texto, sobre_rojo=False, parent=None):
        super().__init__(texto, parent)
        self.sobre_rojo = sobre_rojo
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setWeight(QFont.DemiBold)
        self.setFont(f)
        self.setAlignment(Qt.AlignCenter)
        self.setContentsMargins(7, 2, 7, 2)
        self._estilo()
        qconfig.themeChanged.connect(self._estilo)

    def _estilo(self, *_):
        if self.sobre_rojo:
            self.setStyleSheet("color:rgba(255,255,255,0.92);background:rgba(255,255,255,0.18);"
                               "border-radius:6px;")
        else:
            borde = c("borde2").name(QColor.HexArgb)
            self.setStyleSheet(f"color:{c('texto3').name()};background:transparent;"
                               f"border:1px solid {borde};border-radius:6px;")
