"""Piezas compartidas de la interfaz: zona de captura, tarjetas, bloques, avisos, WhatsApp."""
import os
import re
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QMimeData, QRectF, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLayout,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, InfoBar,
                            InfoBarPosition, PushButton, SpinBox, StrongBodyLabel, SubtitleLabel,
                            TransparentToolButton, isDarkTheme, themeColor)

import fuentes
import motor

# Atajos de teclado como se escriben en cada sistema (en Mac la tecla es ⌘)
CTRL = "⌘" if sys.platform == "darwin" else "Ctrl+"
EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
NOMBRES_PAQUETE = {"ESENCIAL": "Esencial", "INTERMEDIO": "Intermedio", "COMPLETO": "Completo",
                   "PREMIUM": "Premium"}
COLOR_PAQUETE = {"ESENCIAL": "#8e8e96", "INTERMEDIO": "#4f8fe0", "COMPLETO": "#e0262b",
                 "PREMIUM": "#d4a73c"}
COLOR_ESTADO = {"Reservado": "#f5b041", "Abonado": "#5dade2", "Pagado": "#52be80"}
COLORES_AVATAR = ["#c0392b", "#2e86c1", "#7d3c98", "#16a085", "#d35400", "#2c3e50", "#b03a2e", "#1e8449"]
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

    def __init__(self, datos, cfg, destino=None, calidad=None, vista=False):
        super().__init__()
        self.datos, self.cfg, self.destino, self.calidad, self.vista = datos, cfg, destino, calidad, vista

    def run(self):
        try:
            if self.vista:  # vista en vivo: PhotoCraft queda abierto entre un cambio y otro
                ruta = motor.generar_vista(self.datos, self.cfg, self.destino, self.calidad or 80)
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
            motor._cache_fuentes = None
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


class ZonaCaptura(QLabel):
    """Recuadro donde se suelta, pega o elige la captura del pago."""
    cambiada = Signal(str)

    def __init__(self, alto=150, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setFixedHeight(alto)
        self.setCursor(Qt.PointingHandCursor)
        self.setWordWrap(True)
        self.ruta = None
        self.error = False
        self.limpiar()

    def limpiar(self):
        self.ruta = None
        self.setPixmap(QPixmap())
        self.setText(f"Arrastra aquí la captura del pago\no haz clic para buscarla · {CTRL}V para pegarla")
        self.setStyleSheet(f"color: {'#9a9a9f' if isDarkTheme() else '#6b6b70'}; font-size: 13px;")
        self.update()

    def marcar_error(self, si):
        self.error = si
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(255, 255, 255, 10) if isDarkTheme() else QColor(0, 0, 0, 8))
        if self.ruta:
            pen = QPen(themeColor(), 1.6)
        elif self.error:
            pen = QPen(QColor("#e0262b"), 1.8, Qt.DashLine)
        else:
            pen = QPen(QColor(120, 120, 128), 1.6, Qt.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        p.end()
        super().paintEvent(e)

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
        pix = QPixmap(ruta)
        if pix.isNull():
            aviso(self, "error", "Imagen", "No se pudo abrir esa imagen.")
            return
        self.ruta = ruta
        self.error = False
        self.setPixmap(pix.scaled(self.width() - 20, self.height() - 16,
                                  Qt.KeepAspectRatio, Qt.SmoothTransformation))
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

    def __init__(self, widgets=(), max_columnas=2, ancho_min=240, espacio=12, parent=None):
        super().__init__(parent)
        self.max_columnas = max_columnas
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
        return max(1, min(self.max_columnas, (ancho + esp) // (self.ancho_min + esp)))

    def _acomodar(self, forzar=False):
        cols = self._columnas_para(self.width()) if self.width() > 1 else self.max_columnas
        if cols == self.columnas and not forzar:
            return
        self.columnas = cols
        for w in self.widgets:
            self.g.removeWidget(w)
        for i, w in enumerate(self.widgets):
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


class TarjetaPaquete(CardWidget):
    """Tarjeta seleccionable: franja de color del paquete, nombre, servicios y precio."""
    elegida = Signal(str)

    def __init__(self, clave, paquete, destacado=False, parent=None):
        super().__init__(parent)
        self.clave = clave
        self.color = QColor(COLOR_PAQUETE.get(clave, "#888888"))
        self.seleccionada = False
        self.setFixedHeight(84)
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 9, 12, 9)
        v.setSpacing(0)
        fila = QHBoxLayout()
        fila.addWidget(StrongBodyLabel(NOMBRES_PAQUETE.get(clave, clave.title()).upper()))
        fila.addStretch(1)
        if destacado:
            sello = QLabel("MÁS VENDIDO")
            sello.setStyleSheet("background:#e0262b;color:white;border-radius:8px;padding:1px 7px;"
                                "font-size:9px;font-weight:700;")
            fila.addWidget(sello)
        v.addLayout(fila)
        v.addWidget(CaptionLabel(f"{len(paquete.get('incluye', []))} servicios"))
        v.addStretch(1)
        self.precio = SubtitleLabel(q(paquete["precio"]))
        v.addWidget(self.precio)
        self.clicked.connect(lambda: self.elegida.emit(self.clave))

    def actualizar_precio(self, precio):
        self.precio.setText(q(precio))

    def marcar(self, si):
        self.seleccionada = si
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawRoundedRect(QRectF(5, 10, 4, self.height() - 20), 2, 2)
        if self.seleccionada:
            p.setPen(QPen(themeColor(), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        p.end()


class Avatar(QWidget):
    """Círculo de color con las iniciales del cliente."""

    def __init__(self, nombre, tam=28, parent=None):
        super().__init__(parent)
        self.texto = iniciales(nombre)
        self.color = QColor(COLORES_AVATAR[sum(map(ord, nombre)) % len(COLORES_AVATAR)])
        self.setFixedSize(tam, tam)

    def poner(self, nombre):
        self.texto = iniciales(nombre)
        self.color = QColor(COLORES_AVATAR[sum(map(ord, nombre)) % len(COLORES_AVATAR)])
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(self.rect())
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(int(self.height() * 0.38))
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(self.rect(), Qt.AlignCenter, self.texto)
        p.end()


class BarraPago(QWidget):
    """«Q600 de Q1,500» con una barra fina de cuánto lleva pagado (roja; verde si ya pagó todo)."""

    def __init__(self, pagado, total, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pagado, self.total = pagado, total
        self.setMinimumHeight(34)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(QColor("#c8c8cd") if isDarkTheme() else QColor("#444"))
        alto = self.height()
        p.drawText(QRectF(10, alto / 2 - 15, self.width() - 20, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{q(self.pagado)} de {q(self.total)}")
        y = alto / 2 + 5
        ancho = self.width() - 20
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30) if isDarkTheme() else QColor(0, 0, 0, 25))
        p.drawRoundedRect(QRectF(10, y, ancho, 4), 2, 2)
        frac = min(self.pagado / self.total, 1) if self.total else 0
        completo = frac >= 1
        p.setBrush(QColor("#52be80") if completo else QColor("#e0262b"))
        p.drawRoundedRect(QRectF(10, y, max(ancho * frac, 4), 4), 2, 2)
        p.end()


def etiqueta_estado(estado):
    """Píldora de color para Reservado / Abonado / Pagado."""
    color = QColor(COLOR_ESTADO.get(estado, "#999999"))
    lab = QLabel(estado)
    lab.setAlignment(Qt.AlignCenter)
    lab.setStyleSheet(f"background: rgba({color.red()},{color.green()},{color.blue()},45);"
                      f"color: {color.name()}; border-radius: 10px; padding: 2px 10px;"
                      "font-size: 12px; font-weight: 600;")
    return lab


class Kpi(CardWidget):
    """Tarjeta de indicador (título pequeño + valor grande)."""

    def __init__(self, titulo, color=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(78)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 10, 16, 10)
        v.addWidget(CaptionLabel(titulo))
        self.valor = SubtitleLabel("—")
        if color:
            self.valor.setTextColor(QColor(color), QColor(color))
        v.addWidget(self.valor)

    def poner(self, texto):
        self.valor.setText(texto)


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


class _Cabecera(QWidget):
    clicked = Signal()

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)


class Bloque(CardWidget):
    """Bloque plegable numerado. Cerrado muestra un resumen de una línea y ✓ si está completo."""
    pedir_abrir = Signal(object)

    def __init__(self, numero, titulo, parent=None):
        super().__init__(parent)
        self.setBorderRadius(10)
        self.abierto = False
        self.completo = False
        self.numero = numero
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 14)
        v.setSpacing(10)
        self.cab = _Cabecera()
        self.cab.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self.cab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self.circulo = QLabel(str(numero))
        self.circulo.setFixedSize(26, 26)
        self.circulo.setAlignment(Qt.AlignCenter)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        self.titulo = StrongBodyLabel(titulo)
        self.resumen = CaptionLabel("")
        self.resumen.setWordWrap(True)
        tv.addWidget(self.titulo)
        tv.addWidget(self.resumen)
        self.estado = CaptionLabel("pendiente")
        self.flecha = TransparentToolButton(FIF.CHEVRON_RIGHT_MED)
        self.flecha.setFixedSize(28, 28)
        self.flecha.clicked.connect(lambda: self.pedir_abrir.emit(self))
        h.addWidget(self.circulo)
        h.addLayout(tv, 1)
        h.addWidget(self.estado)
        h.addWidget(self.flecha)
        self.cab.clicked.connect(lambda: self.pedir_abrir.emit(self))
        v.addWidget(self.cab)
        self.contenido = QWidget()
        self.cuerpo = QVBoxLayout(self.contenido)
        self.cuerpo.setContentsMargins(36, 0, 0, 0)
        self.cuerpo.setSpacing(10)
        v.addWidget(self.contenido)
        self._pintar()

    def abrir(self, si):
        self.abierto = si
        self._pintar()

    def poner_estado(self, completo, resumen):
        self.completo = completo
        self.resumen.setText(resumen)
        self._pintar()

    def _pintar(self):
        self.contenido.setVisible(self.abierto)
        self.resumen.setVisible(not self.abierto)
        self.flecha.setIcon(FIF.CHEVRON_DOWN_MED if self.abierto else FIF.CHEVRON_RIGHT_MED)
        if self.completo:
            fondo, texto = "#2e9e57", "white"
            self.circulo.setText("✓")
            self.estado.setText("listo")
            self.estado.setTextColor(QColor("#2e9e57"), QColor("#52be80"))
        else:
            fondo = "#e0262b" if self.abierto else ("#3a3a40" if isDarkTheme() else "#d5d5da")
            texto = "white" if (self.abierto or isDarkTheme()) else "#333"
            self.circulo.setText(str(self.numero))
            self.estado.setText("editando" if self.abierto else "pendiente")
            self.estado.setTextColor(QColor("#e0262b") if self.abierto else QColor("#777"),
                                     QColor("#ff5a5f") if self.abierto else QColor("#999"))
        self.circulo.setStyleSheet(f"background:{fondo};color:{texto};border-radius:13px;"
                                   "font-weight:700;font-size:12px;")
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.abierto:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(themeColor(), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
            p.end()
