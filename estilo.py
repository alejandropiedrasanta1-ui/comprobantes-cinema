"""Sistema de diseño (2026): colores, superficies, píldoras, montos e íconos comunes a todas las pantallas.
Modo oscuro grafito y modo claro; el rojo de la marca solo en acciones principales y estados activos.
Todo se pinta en paintEvent leyendo el tema actual, así cambia al instante con Oscuro/Claro."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
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
               texto3="#71717A", punto=(255, 255, 255, 14))
_CLARO = dict(fondo="#F5F5F7", panel="#EEEEF1", sup="#FFFFFF", sup2="#F8F8FA", sup3="#EFEFF3",
              borde=(0, 0, 0, 20), borde2=(0, 0, 0, 34), texto="#111114", texto2="#52525B",
              texto3="#8A8A93", punto=(0, 0, 0, 18))


def c(nombre):
    """Color del tema actual (fondo, panel, sup, sup2, sup3, borde, borde2, texto, texto2, texto3, punto)."""
    v = (_OSCURO if isDarkTheme() else _CLARO)[nombre]
    return QColor(*v) if isinstance(v, tuple) else QColor(v)


def alfa(color, a):
    col = QColor(color)
    col.setAlpha(a)
    return col


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
    selección rojo, y clic (cursor de mano + señal clicked)."""
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
        self.setAttribute(Qt.WA_StyledBackground, False)
        if clicable:
            self.setCursor(Qt.PointingHandCursor)

    def marcar(self, si):
        self.seleccionada = si
        self.update()

    def enterEvent(self, e):
        self._encima = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._encima = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self.clicable and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fondo = c("sup2" if self.nivel == 2 else "sup")
        if self.clicable and self._encima and not self.seleccionada:
            fondo = c("sup2" if self.nivel == 1 else "sup3")
        if self.seleccionada:
            p.setPen(Qt.NoPen)
            for i, a in enumerate((10, 6, 3)):          # brillo suave alrededor
                p.setBrush(alfa(ROJO, a))
                p.drawRoundedRect(r.adjusted(-2 - 2 * i, -2 - 2 * i, 2 + 2 * i, 2 + 2 * i),
                                  self.radio + 2 + 2 * i, self.radio + 2 + 2 * i)
        p.setPen(QPen(c("borde"), 1))
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
        if self.seleccionada or self.resaltada:
            p.setPen(QPen(QColor(ROJO) if self.seleccionada else alfa(self.acento or QColor(ROJO), 150), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, -0.6), self.radio, self.radio)
        p.end()


class Pildora(QWidget):
    """Etiqueta redondeada pintada (estado, conteo, sello). Fondo = color con transparencia."""

    def __init__(self, texto, color=None, solida=False, icono_nombre=None, tam_letra=12, alto=24, parent=None):
        super().__init__(parent)
        self.texto, self.color, self.solida, self.icono_nombre = texto, color, solida, icono_nombre
        self.tam_letra, self.alto = tam_letra, alto
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._medir()

    def poner(self, texto=None, color=None):
        if texto is not None:
            self.texto = texto
        if color is not None:
            self.color = color
        self._medir()
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
        color = QColor(self.color) if self.color else c("texto2")
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.solida:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            texto = QColor("white")
        else:
            p.setPen(QPen(alfa(color, 70), 1))
            p.setBrush(alfa(color, 34 if isDarkTheme() else 26))
            texto = color if self.color else c("texto2")
        p.drawRoundedRect(r, self.alto / 2, self.alto / 2)
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
    """Monto grande con cifras tabulares (p. ej. el saldo pendiente)."""

    def __init__(self, texto="Q0", px=30, color=None, parent=None):
        super().__init__(texto, parent)
        self.px, self.color = px, color
        self.setFont(fuente_numeros(px, QFont.Bold))
        self._pintar_color()
        qconfig.themeChanged.connect(self._pintar_color)

    def _pintar_color(self, *_):
        col = QColor(self.color) if self.color else c("texto")
        self.setStyleSheet(f"color:{col.name()};background:transparent;")

    def poner_color(self, color):
        self.color = color
        self._pintar_color()


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
