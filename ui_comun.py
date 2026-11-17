"""Piezas compartidas de la interfaz: zona de captura, tarjetas, bloques, avisos, WhatsApp."""
import os
import re
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QImage, QImageReader, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLayout,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon as FIF, InfoBar,
                            InfoBarPosition, PushButton, SpinBox, StrongBodyLabel, SubtitleLabel,
                            TransparentToolButton, isDarkTheme, themeColor)

import estilo
import fuentes
import motor
from estilo import Cifra, Icono, Pildora, Tarjeta

# Atajos de teclado como se escriben en cada sistema (en Mac la tecla es ⌘)
CTRL = "⌘" if sys.platform == "darwin" else "Ctrl+"
EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
NOMBRES_PAQUETE = {"ESENCIAL": "Esencial", "INTERMEDIO": "Intermedio", "COMPLETO": "Completo",
                   "PREMIUM": "Premium"}
COLOR_PAQUETE = {"ESENCIAL": "#A1A1AA", "INTERMEDIO": estilo.AZUL, "COMPLETO": estilo.ROJO,
                 "PREMIUM": "#D4A73C"}
ICONO_PAQUETE = {"ESENCIAL": "camara", "INTERMEDIO": "video", "COMPLETO": "corona", "PREMIUM": "diamante"}
COLOR_ESTADO = {"Reservado": estilo.AMBAR, "Abonado": estilo.AZUL, "Pagado": estilo.VERDE}
COLORES_AVATAR = ["#7C3AED", "#E5252A", "#EA580C", "#0EA5E9", "#16A34A", "#DB2777", "#D97706", "#2563EB"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def q(valor):
    return motor.quetzales(valor)


def fecha_larga(d: date):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def faltan(d: date):
    dias = (d - date.today()).days
    if dias == 0:
        return "es hoy"
    if dias == 1:
        return "es mañana"
    return f"faltan {dias} días" if dias > 0 else f"fue hace {-dias} días"


def formatear_telefono(texto):
    """+502 1234 5678 a partir de lo que se escriba (8 dígitos o 502 + 8 dígitos)."""
    d = re.sub(r"\D", "", texto)
    if len(d) == 8:
        d = "502" + d
    if len(d) == 11 and d.startswith("502"):
        return f"+502 {d[3:7]} {d[7:]}"
    return texto.strip()


def digitos_telefono(texto):
    d = re.sub(r"\D", "", texto)
    return "502" + d if len(d) == 8 else d


def iniciales(nombre):
    partes = [p for p in re.split(r"[\s&]+", nombre) if p and p.lower() not in ("y", "de", "del", "la")]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def abrir(ruta):
    if ruta and Path(ruta).exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))


def copiar_imagen(ruta):
    """Copia el comprobante: como imagen (WhatsApp Web/Escritorio) y como archivo."""
    datos = QMimeData()
    datos.setImageData(QImage(str(ruta)))
    datos.setUrls([QUrl.fromLocalFile(str(ruta))])
    QApplication.clipboard().setMimeData(datos)


def abrir_whatsapp(telefono, nombre):
    """Abre el chat de WhatsApp del cliente con un saludo; el comprobante queda copiado para pegar."""
    numero = digitos_telefono(telefono)
    if len(numero) < 10:
        return False
    texto = f"Hola {nombre.strip()}, les compartimos su comprobante de pago. ¡Gracias por confiar en Cinema Productions!"
    QDesktopServices.openUrl(QUrl(f"https://wa.me/{numero}?text={quote(texto)}"))
    return True


def aviso(padre, tipo, titulo, texto, duracion=4000, ruta_abrir=None):
    barra = getattr(InfoBar, tipo)(titulo, texto, isClosable=True, duration=duracion,
                                   position=InfoBarPosition.TOP_RIGHT, parent=padre.window())
    if ruta_abrir:
        b = PushButton("Abrir")
        b.clicked.connect(lambda: abrir(ruta_abrir))
        barra.addWidget(b)
    return barra


class Trabajo(QThread):
    """Genera el comprobante (o la vista previa) con PhotoCraft sin congelar la ventana."""
    listo = Signal(str)
    fallo = Signal(str)

    def __init__(self, datos, cfg, destino=None, calidad=None, vista=False, lado=None):
        super().__init__()
        self.datos, self.cfg, self.destino, self.calidad, self.vista = datos, cfg, destino, calidad, vista
        self.lado = lado

    def run(self):
        try:
            if self.vista:  # vista en vivo: PhotoCraft queda abierto entre un cambio y otro
                ruta = motor.generar_vista(self.datos, self.cfg, self.destino, self.calidad or 80, self.lado)
            else:
                ruta = motor.generar(self.datos, self.cfg, self.destino, self.calidad)
            self.listo.emit(str(ruta))
        except Exception as e:  # se muestra al usuario
            traceback.print_exc()
            self.fallo.emit(str(e))


class Revision(QThread):
    """Al abrir: comprueba que PhotoCraft tenga las fuentes del diseño e instala las que falten."""
    listo = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

    def run(self):
        try:
            faltan_f = fuentes.faltantes(motor._fuentes_instaladas(self.cfg))
            if not faltan_f:
                return
            hechos = fuentes.instalar(faltan_f)
            motor.olvidar_fuentes()
            siguen = fuentes.faltantes(motor._fuentes_instaladas(self.cfg))
            if siguen:
                self.listo.emit("Faltan las fuentes del diseño (" + ", ".join(siguen) + "). "
                                "Ve a Ajustes › Fuentes del diseño y elige la carpeta donde están.")
            elif hechos:
                self.listo.emit("Se instalaron las fuentes del diseño: " + ", ".join(faltan_f) + ".")
        except Exception as e:  # informativo; el programa sigue funcionando
            self.listo.emit(f"No se pudieron revisar las fuentes: {e}")


class Monto(SpinBox):
    """Campo de quetzales (Q 3,500). Corrige que, con PySide6 6.12, el texto interno del SpinBox
    de Fluent-Widgets queda de 1 px de ancho y el número no se ve."""
    ANCHO_BOTONES = 76

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 1_000_000)
        self.setSingleStep(100)
        self.setPrefix("Q ")
        self.setGroupSeparatorShown(True)

    def _ajustar(self):
        self.lineEdit().setGeometry(0, 0, max(self.width() - self.ANCHO_BOTONES, 20), self.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._ajustar()

    def showEvent(self, e):
        super().showEvent(e)
        self._ajustar()

    def changeEvent(self, e):
        super().changeEvent(e)
        self._ajustar()


class ZonaCaptura(QWidget):
    """Recuadro punteado donde se suelta, pega o elige la captura del pago.
    Con imagen: miniatura, ✓ verde y el nombre del archivo."""
    cambiada = Signal(str)

    def __init__(self, alto=150, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(alto)
        self.setCursor(Qt.PointingHandCursor)
        self.ruta = None
        self.error = False
        self._mini = None
        self._encima = False
        self.limpiar()

    def limpiar(self):
        self.ruta = None
        self._mini = None
        self.update()

    def marcar_error(self, si):
        self.error = si
        self.update()

    def enterEvent(self, e):
        self._encima = True
        self.update()

    def leaveEvent(self, e):
        self._encima = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.ruta:
            p.setPen(QPen(estilo.alfa(estilo.VERDE, 110), 1.2))
            p.setBrush(estilo.c("sup2"))
        else:
            color = QColor(estilo.ROJO) if self.error else estilo.c("texto2" if self._encima else "borde2")
            pen = QPen(color, 1.4, Qt.CustomDashLine)
            pen.setDashPattern([5, 4])
            p.setPen(pen)
            p.setBrush(estilo.alfa(estilo.ROJO, 14) if self.error else
                       (estilo.c("sup2") if self._encima else Qt.NoBrush))
        p.drawRoundedRect(r, 12, 12)
        f = QFont(self.font())
        if self.ruta and self._mini:
            alto = r.height() - 20
            ancho = min(alto * self._mini.width() / max(self._mini.height(), 1), r.width() * 0.4)
            caja = QRectF(r.left() + 10, r.top() + 10, ancho, alto)
            camino = QPainterPath()
            camino.addRoundedRect(caja, 8, 8)
            p.save()
            p.setClipPath(camino)
            p.drawPixmap(caja, self._mini, QRectF(self._mini.rect()))
            p.restore()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(estilo.VERDE))
            ck = QRectF(caja.right() - 12, caja.top() - 6, 20, 20)
            p.drawEllipse(ck)
            p.setPen(QPen(QColor("white"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(ck.left() + 5.5, ck.center().y()), QPointF(ck.left() + 8.8, ck.bottom() - 6),
                            QPointF(ck.right() - 5, ck.top() + 6.5)])
            x = caja.right() + 18
            f.setPixelSize(14)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(estilo.c("texto"))
            cy = r.center().y()
            p.drawText(QRectF(x, cy - 30, r.right() - x - 10, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       "Captura del pago lista")
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(estilo.c("texto3"))
            nombre = p.fontMetrics().elidedText(Path(self.ruta).name, Qt.ElideMiddle, int(r.right() - x - 10))
            p.drawText(QRectF(x, cy - 8, r.right() - x - 10, 18), Qt.AlignLeft | Qt.AlignVCenter, nombre)
            p.drawText(QRectF(x, cy + 10, r.right() - x - 10, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Clic para cambiarla · {CTRL}V para pegar otra")
        else:
            lado = 26
            color_ico = QColor(estilo.ROJO) if self.error else estilo.c("texto2")
            arriba = r.center().y() - (lado + 40) / 2
            p.drawPixmap(QPointF(r.center().x() - lado / 2, arriba), estilo.pixmap_icono("recibo", color_ico, lado))
            f.setPixelSize(13)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(estilo.ROJO) if self.error else estilo.c("texto"))
            p.drawText(QRectF(r.left() + 8, arriba + lado + 6, r.width() - 16, 18), Qt.AlignCenter,
                       "Falta la captura del pago" if self.error else "Arrastra la captura del pago")
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(estilo.c("texto3"))
            p.drawText(QRectF(r.left() + 8, arriba + lado + 24, r.width() - 16, 18), Qt.AlignCenter,
                       f"o haz clic para buscarla · {CTRL}V para pegarla")
        p.end()

    def mousePressEvent(self, e):
        self.buscar()

    def buscar(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Captura del comprobante de pago", "",
                                              "Imágenes (*.jpg *.jpeg *.png *.webp *.bmp)")
        if ruta:
            self.usar(ruta)

    def pegar(self):
        datos = QApplication.clipboard().mimeData()
        for url in datos.urls():
            if url.toLocalFile().lower().endswith(EXT_IMAGEN):
                return self.usar(url.toLocalFile())
        if datos.hasImage():
            img = QApplication.clipboard().image()
            if not img.isNull():
                ruta = os.path.join(tempfile.gettempdir(), f"cinema_captura_{id(self)}.png")
                img.save(ruta)
                return self.usar(ruta)
        aviso(self, "warning", "Nada para pegar", "No hay ninguna imagen copiada.")

    def usar(self, ruta):
        lector = QImageReader(ruta)
        lector.setAutoTransform(True)
        tam = lector.size()
        if tam.isValid() and tam.height() > 400:   # miniatura sin decodificar la foto completa
            lector.setScaledSize(tam.scaled(10_000, 400, Qt.KeepAspectRatio))
        img = lector.read()
        if img.isNull():
            aviso(self, "error", "Imagen", "No se pudo abrir esa imagen.")
            return
        self.ruta = ruta
        self.error = False
        self._mini = QPixmap.fromImage(img)
        self.update()
        self.cambiada.emit(ruta)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.toLocalFile().lower().endswith(EXT_IMAGEN):
                self.usar(url.toLocalFile())
                return


class Rejilla(QWidget):
    """Coloca widgets en columnas que se reacomodan solas según el ancho disponible:
    en pantallas grandes van lado a lado y en ventanas chicas (MacBook, laptops) pasan a una sola columna."""

    def __init__(self, widgets=(), max_columnas=2, ancho_min=240, espacio=12, parent=None, validas=None,
                 misma_altura=False):
        super().__init__(parent)
        self.max_columnas = max_columnas
        self.misma_altura = misma_altura     # las tarjetas de una fila se estiran al alto de la más alta
        self.validas = sorted(validas) if validas else None   # p. ej. (1, 2, 4): nunca 3 + 1 sueltas
        self.ancho_min = ancho_min
        self.columnas = 0
        self.widgets = []
        self.g = QGridLayout(self)
        self.g.setContentsMargins(0, 0, 0, 0)
        self.g.setHorizontalSpacing(espacio)
        self.g.setVerticalSpacing(espacio)
        # la rejilla puede quedar más angosta que sus columnas actuales: así se entera de que debe reacomodarse
        self.g.setSizeConstraint(QLayout.SetNoConstraint)
        for w in widgets:
            self.agregar(w)

    def agregar(self, w):
        self.widgets.append(w)
        w.setParent(self)
        self._acomodar(forzar=True)

    def _columnas_para(self, ancho):
        esp = self.g.horizontalSpacing()
        n = max(1, min(self.max_columnas, (ancho + esp) // (self.ancho_min + esp)))
        if self.validas:
            n = max([v for v in self.validas if v <= n] or [1])
        return n

    def _acomodar(self, forzar=False):
        cols = self._columnas_para(self.width()) if self.width() > 1 else self.max_columnas
        if cols == self.columnas and not forzar:
            return
        self.columnas = cols
        for w in self.widgets:
            self.g.removeWidget(w)
        for i, w in enumerate(self.widgets):
            if self.misma_altura:
                self.g.addWidget(w, i // cols, i % cols)
            else:
                self.g.addWidget(w, i // cols, i % cols, Qt.AlignTop)
        for c in range(self.max_columnas):
            self.g.setColumnStretch(c, 1 if c < cols else 0)
        self.updateGeometry()

    def minimumSizeHint(self):
        ancho = max((w.minimumSizeHint().width() for w in self.widgets), default=0)
        return QSize(min(ancho, self.ancho_min), self.g.minimumSize().height())

    def sizeHint(self):
        return QSize(self.g.sizeHint().width(), self.g.sizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._acomodar()


class TarjetaPaquete(Tarjeta):
    """Tarjeta compacta para elegir paquete: nombre con su color, precio grande, servicios, círculo de
    selección y sello «Más vendido». Todo pintado (se ve igual en Windows y Mac)."""
    elegida = Signal(str)

    def __init__(self, clave, paquete, destacado=False, parent=None):
        super().__init__(parent, clicable=True, nivel=2)
        self.clave = clave
        self.nombre = NOMBRES_PAQUETE.get(clave, clave.title())
        self.precio = paquete["precio"]
        self.servicios = len(paquete.get("incluye", []))
        self.destacado = destacado
        self.color = QColor(COLOR_PAQUETE.get(clave, "#888888"))
        self.setFixedHeight(96)
        self.setMinimumWidth(118)
        self.setToolTip(f"{self.nombre} · {q(self.precio)} · {self.servicios} servicios")
        self.clicked.connect(lambda: self.elegida.emit(self.clave))

    def actualizar_precio(self, precio):
        self.precio = precio
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        angosta = w < 136          # sin círculo de selección: el anillo rojo ya marca la elegida
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(12 if angosta else 14, 17, 6 if angosta else 7, 6 if angosta else 7))
        f = QFont(self.font())
        f.setPixelSize(12 if angosta else 13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(estilo.c("texto"))
        x = 23 if angosta else 27
        disponible = int(w - x - (8 if angosta else 34))
        p.drawText(QRectF(x, 10, disponible, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.nombre, Qt.ElideRight, disponible))
        # círculo de selección
        circ = QRectF(w - 28, 12, 16, 16)
        if angosta:
            pass
        elif self.seleccionada:
            p.setPen(QPen(QColor(estilo.ROJO), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(circ)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(estilo.ROJO))
            p.drawEllipse(circ.adjusted(4, 4, -4, -4))
        else:
            p.setPen(QPen(estilo.c("borde2"), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(circ)
        p.setFont(estilo.fuente_numeros(21, QFont.Bold, self.font()))
        p.setPen(estilo.c("texto"))
        p.drawText(QRectF(14, 32, w - 24, 30), Qt.AlignLeft | Qt.AlignVCenter, q(self.precio))
        f.setPixelSize(12)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(estilo.c("texto3"))
        p.drawText(QRectF(14, h - 30, w - 24, 18), Qt.AlignLeft | Qt.AlignVCenter, f"{self.servicios} servicios")
        if self.destacado:
            f.setPixelSize(9)
            f.setWeight(QFont.Bold)
            p.setFont(f)
            texto = "MÁS VENDIDO"
            ancho = p.fontMetrics().horizontalAdvance(texto) + 12
            caja = QRectF(w - ancho - 10, h - 28, ancho, 16)
            if caja.left() > 14 + p.fontMetrics().horizontalAdvance("12 servicios") + 30:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(estilo.ROJO))
                p.drawRoundedRect(caja, 8, 8)
                p.setPen(QColor("white"))
                p.drawText(caja, Qt.AlignCenter, texto)
        p.end()


class Avatar(QWidget):
    """Círculo de color con las iniciales del cliente."""

    def __init__(self, nombre, tam=28, parent=None):
        super().__init__(parent)
        self.texto = iniciales(nombre)
        self.color = color_avatar(nombre)
        self.setFixedSize(tam, tam)

    def poner(self, nombre):
        self.texto = iniciales(nombre)
        self.color = color_avatar(nombre)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(self.rect()))
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(int(self.height() * 0.36))
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(self.rect(), Qt.AlignCenter, self.texto)
        p.end()


def color_avatar(nombre):
    return QColor(COLORES_AVATAR[sum(map(ord, nombre or "?")) % len(COLORES_AVATAR)])


class BarraPago(QWidget):
    """Barra fina de cuánto lleva pagado (roja; verde si ya pagó todo)."""

    def __init__(self, pagado=0, total=0, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pagado, self.total = pagado, total
        self.setFixedHeight(8)

    def poner(self, pagado, total):
        self.pagado, self.total = pagado, total
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(estilo.c("sup3"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        frac = min(self.pagado / self.total, 1) if self.total else 0
        p.setBrush(QColor(estilo.VERDE if frac >= 1 else estilo.ROJO))
        p.drawRoundedRect(QRectF(r.left(), r.top(), max(r.width() * frac, r.height()), r.height()),
                          r.height() / 2, r.height() / 2)
        p.end()


def etiqueta_estado(estado):
    """Píldora de color para Reservado / Abonado / Pagado."""
    return Pildora(estado, COLOR_ESTADO.get(estado, "#999999"))


class MiniGrafico(QWidget):
    """Gráfico diminuto de una tarjeta de indicador: línea con relleno, barras o puntos de calendario."""

    def __init__(self, tipo="linea", color=None, parent=None):
        super().__init__(parent)
        self.tipo, self.color = tipo, color
        self.serie = []
        self.setFixedSize(QSize(70, 40) if tipo == "puntos" else QSize(104, 40))

    def poner(self, serie):
        self.serie = list(serie or [])
        self.update()

    def paintEvent(self, e):
        if not self.serie:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.color) if self.color else estilo.c("texto2")
        w, h = self.width(), self.height()
        if self.tipo == "puntos":      # días del mes: 0 nada, 1 hay evento, 2 hoy
            cols, lado = 7, 6
            for i, v in enumerate(self.serie[:35]):
                x = (i % cols) * (lado + 4)
                y = (i // cols) * (lado + 2.5)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(estilo.ROJO) if v == 1 else (estilo.c("texto") if v == 2 else estilo.c("sup3")))
                p.drawEllipse(QRectF(x, y, lado, lado))
        elif self.tipo == "barras":
            n = len(self.serie)
            maximo = max(self.serie) or 1
            ancho = (w - (n - 1) * 3) / n
            for i, v in enumerate(self.serie):
                alto = max(3, (h - 2) * v / maximo)
                p.setPen(Qt.NoPen)
                p.setBrush(color if i == n - 1 else estilo.alfa(color, 110))
                p.drawRoundedRect(QRectF(i * (ancho + 3), h - alto, ancho, alto), 1.5, 1.5)
        else:
            n = len(self.serie)
            maximo = max(self.serie) or 1
            pts = [QPointF(3 + i * (w - 6) / max(n - 1, 1), h - 4 - (h - 10) * v / maximo)
                   for i, v in enumerate(self.serie)]
            camino = QPainterPath(pts[0])
            for a, b in zip(pts, pts[1:]):
                medio = (a.x() + b.x()) / 2
                camino.cubicTo(QPointF(medio, a.y()), QPointF(medio, b.y()), b)
            relleno = QPainterPath(camino)
            relleno.lineTo(pts[-1].x(), h)
            relleno.lineTo(pts[0].x(), h)
            relleno.closeSubpath()
            degr = QLinearGradient(0, 0, 0, h)
            degr.setColorAt(0, estilo.alfa(color, 70))
            degr.setColorAt(1, estilo.alfa(color, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(degr)
            p.drawPath(relleno)
            p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(camino)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(pts[-1], 2.6, 2.6)
        p.end()


class Kpi(Tarjeta):
    """Tarjeta de indicador: ícono en cuadrito, título, cifra grande y un mini gráfico."""

    def __init__(self, titulo, color=None, icono_nombre="recibo", grafico="linea", parent=None):
        super().__init__(parent)
        self.setFixedHeight(92)
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(12)
        h.addWidget(Icono(icono_nombre, 20, color=color or None, fondo=color or "#8A8A93", caja=40), 0,
                    Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(0)
        v.addWidget(CaptionLabel(titulo))
        self.valor = Cifra("—", 26)
        v.addWidget(self.valor)
        v.addStretch(1)
        h.addLayout(v, 1)
        self.mini = MiniGrafico(grafico, color)
        h.addWidget(self.mini, 0, Qt.AlignBottom)

    def poner(self, texto, serie=None):
        self.valor.setText(texto)
        if serie is not None:
            self.mini.poner(serie)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.mini.setVisible(self.width() > 250)


def etiqueta_valor(titulo, valor=""):
    """Fila 'Título ........ valor' para paneles de detalle."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(BodyLabel(titulo))
    h.addStretch(1)
    val = StrongBodyLabel(valor)
    h.addWidget(val)
    return w, val


class Pasos(QWidget):
    """«① Cliente y evento ✓ — ② Paquete ✓ — ③ Pago y captura»: verde lo listo, rojo el que sigue.
    Clic en un paso: elegido(índice). En ventanas angostas solo se ve el nombre del paso actual."""
    elegido = Signal(int)

    def __init__(self, titulos, parent=None):
        super().__init__(parent)
        self.titulos = list(titulos)
        self.completos = [False] * len(self.titulos)
        self._cajas = []
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)

    def poner(self, completos):
        self.completos = list(completos)
        self.update()

    def _actual(self):
        return next((i for i, ok in enumerate(self.completos) if not ok), -1)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = p.fontMetrics()
        d, unir, sep = 20, 26, 8
        actual = self._actual()
        anchos = [d + sep + fm.horizontalAdvance(t) for t in self.titulos]
        completo = sum(anchos) + unir * (len(self.titulos) - 1) <= self.width()
        x, cy = 0.0, self.height() / 2
        self._cajas = []
        for i, t in enumerate(self.titulos):
            ok, es_actual = self.completos[i], i == actual
            circ = QRectF(x, cy - d / 2, d, d)
            p.setPen(Qt.NoPen)
            if ok:
                p.setBrush(QColor(estilo.VERDE))
                p.drawEllipse(circ)
                p.setPen(QPen(QColor("white"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline([QPointF(circ.left() + 5.5, cy), QPointF(circ.left() + 8.6, cy + 3.2),
                                QPointF(circ.right() - 5, cy - 3.6)])
            else:
                if es_actual:
                    p.setBrush(QColor(estilo.ROJO))
                    p.drawEllipse(circ)
                    p.setPen(QColor("white"))
                else:
                    p.setPen(QPen(estilo.c("borde2"), 1.4))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(circ.adjusted(0.7, 0.7, -0.7, -0.7))
                    p.setPen(estilo.c("texto3"))
                g = QFont(f)
                g.setPixelSize(11)
                p.setFont(g)
                p.drawText(circ, Qt.AlignCenter, str(i + 1))
                p.setFont(f)
            fin = circ.right()
            if completo or es_actual or (actual == -1 and i == len(self.titulos) - 1):
                p.setPen(estilo.c("texto") if (ok or es_actual) else estilo.c("texto3"))
                ancho_t = fm.horizontalAdvance(t)
                p.drawText(QRectF(circ.right() + sep, 0, ancho_t + 2, self.height()),
                           Qt.AlignLeft | Qt.AlignVCenter, t)
                fin = circ.right() + sep + ancho_t
            self._cajas.append(QRectF(x, 0, fin - x, self.height()))
            x = fin
            if i < len(self.titulos) - 1:
                p.setPen(QPen(QColor(estilo.VERDE) if ok else estilo.c("borde2"), 1.4))
                p.drawLine(QPointF(x + 8, cy), QPointF(x + unir - 8, cy))
                x += unir
        p.end()

    def mousePressEvent(self, e):
        for i, caja in enumerate(self._cajas):
            if caja.contains(e.position()):
                self.elegido.emit(i)
                return


class _Cabecera(QWidget):
    clicked = Signal()

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)


class Bloque(Tarjeta):
    """Sección del formulario (siempre abierta): ícono, título y una píldora de estado
    («Listo» en verde o «Falta …» en ámbar). abrir(True) solo la resalta."""
    pedir_abrir = Signal(object)

    def __init__(self, numero, titulo, icono_nombre=None, parent=None):
        super().__init__(parent)
        self.abierto = True
        self.completo = False
        self.numero = numero
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 18)
        v.setSpacing(14)
        self.cab = _Cabecera()
        h = QHBoxLayout(self.cab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        if icono_nombre:
            h.addWidget(Icono(icono_nombre, 18))
        self.titulo = StrongBodyLabel(titulo)
        f = self.titulo.font()
        f.setPixelSize(15)
        self.titulo.setFont(f)
        h.addWidget(self.titulo)
        h.addStretch(1)
        self.estado = Pildora("Pendiente")
        h.addWidget(self.estado)
        self.resumen = CaptionLabel("")     # (compatibilidad) el resumen va en la píldora y el tooltip
        self.resumen.hide()
        self.cab.clicked.connect(lambda: self.pedir_abrir.emit(self))
        v.addWidget(self.cab)
        self.contenido = QWidget()
        self.cuerpo = QVBoxLayout(self.contenido)
        self.cuerpo.setContentsMargins(0, 0, 0, 0)
        self.cuerpo.setSpacing(12)
        v.addWidget(self.contenido)

    def abrir(self, si):
        self.resaltada = si and not self.completo
        self.update()

    def poner_estado(self, completo, resumen, falta=None):
        self.completo = completo
        self.resumen.setText(resumen)
        self.setToolTip(resumen)
        if completo:
            self.estado.poner("Listo", estilo.VERDE)
            self.resaltada = False
        else:
            self.estado.poner(("Falta " + falta) if falta else "Pendiente", estilo.AMBAR if falta else None)
        self.update()
