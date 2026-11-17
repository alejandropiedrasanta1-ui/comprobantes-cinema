"""Piezas compartidas de la interfaz: zona de captura, tarjetas, bloques, avisos, WhatsApp."""
import os
import re
import subprocess
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QDate, QEasingCurve, QEvent, QMimeData, QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QImage, QImageReader, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLayout, QSizePolicy,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon as FIF, Flyout, FlyoutAnimationType,
                            InfoBar, InfoBarPosition, LineEdit, PushButton, SpinBox, StrongBodyLabel, SubtitleLabel,
                            ToolTipFilter, TransparentToolButton, isDarkTheme, themeColor)
from qfluentwidgets.components.date_time.fast_calendar_view import FastCalendarView
from qfluentwidgets.components.widgets.line_edit import LineEditButton

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


def mostrar_en_carpeta(ruta):
    """Abre la carpeta del archivo con el archivo ya marcado (Explorador en Windows, Finder en Mac)."""
    ruta = Path(ruta) if ruta else None
    if not ruta or not ruta.exists():
        return
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{ruta}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(ruta)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta.parent)))
    except OSError:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta.parent)))


def abrir_carpeta_si_toca(cfg, ruta, espera_ms=900):
    """Tras generar: abre la carpeta del comprobante (Ajustes › «Abrir la carpeta al terminar»). Espera un
    poco para que primero se vea el «¡Comprobante listo!»."""
    if cfg.get("abrir_carpeta", True):
        QTimer.singleShot(espera_ms, lambda: mostrar_en_carpeta(ruta))


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
        self._t_encima = 0.0         # 0 → 1 al pasar el mouse
        self._t_mini = 1.0           # 0 → 1: la miniatura entra con fundido y crece un poco
        self._arrastrando = False    # hay una imagen encima, a punto de soltarse
        self._fase = 0.0
        self._hormigas = QTimer(self)                 # el borde punteado avanza mientras arrastras
        self._hormigas.setInterval(40)
        self._hormigas.timeout.connect(self._avanzar_borde)
        self.limpiar()

    def _avanzar_borde(self):
        self._fase = (self._fase + 1) % 9
        self.update()

    def _poner_t(self, campo, v):
        setattr(self, campo, v)
        self.update()

    def _arrastre(self, si):
        self._arrastrando = si
        if si and estilo.ANIMAR:
            self._hormigas.start()
        else:
            self._hormigas.stop()
        self.update()

    def limpiar(self):
        self.ruta = None
        self._mini = None
        self.update()

    def marcar_error(self, si):
        self.error = si
        self.update()

    def enterEvent(self, e):
        self._encima = True
        estilo.animar(self, "_ani_encima", self._t_encima, 1.0, 150, lambda v: self._poner_t("_t_encima", v))

    def leaveEvent(self, e):
        self._encima = False
        estilo.animar(self, "_ani_encima", self._t_encima, 0.0, 240, lambda v: self._poner_t("_t_encima", v))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._arrastrando:
            pen = QPen(QColor(estilo.ROJO), 1.8, Qt.CustomDashLine)
            pen.setDashPattern([5, 4])
            pen.setDashOffset(-self._fase)
            p.setPen(pen)
            p.setBrush(estilo.alfa(estilo.ROJO, 26))
        elif self.ruta:
            p.setPen(QPen(estilo.alfa(estilo.VERDE, 110), 1.2))
            p.setBrush(estilo.c("sup2"))
        else:
            color = (QColor(estilo.ROJO) if self.error else
                     estilo.mezclar(estilo.c("borde2"), estilo.c("texto2"), self._t_encima))
            pen = QPen(color, 1.4, Qt.CustomDashLine)
            pen.setDashPattern([5, 4])
            p.setPen(pen)
            p.setBrush(estilo.alfa(estilo.ROJO, 14) if self.error else
                       estilo.alfa(estilo.c("sup2"), int(255 * self._t_encima)))
        p.drawRoundedRect(r, 12, 12)
        f = QFont(self.font())
        if self._arrastrando:                         # «suelta aquí»
            f.setPixelSize(14)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(estilo.ROJO_CLARO))
            p.drawText(r, Qt.AlignCenter, "Suelta la imagen aquí")
            p.end()
            return
        if self.ruta and self._mini:
            bajo = r.height() < 80                       # recuadro apretado: ✓ dentro de la miniatura, 2 renglones
            alto = r.height() - (14 if bajo else 20)
            ancho = min(alto * self._mini.width() / max(self._mini.height(), 1), r.width() * 0.4)
            caja = QRectF(r.left() + (8 if bajo else 10), r.top() + (7 if bajo else 10), ancho, alto)
            t = self._t_mini
            if t < 1:                                 # entra creciendo de 92 % a 100 %
                k = 0.92 + 0.08 * t
                caja = QRectF(caja.center().x() - caja.width() * k / 2, caja.center().y() - caja.height() * k / 2,
                              caja.width() * k, caja.height() * k)
            camino = QPainterPath()
            camino.addRoundedRect(caja, 8, 8)
            p.save()
            p.setOpacity(t)
            p.setClipPath(camino)
            p.drawPixmap(caja, self._mini, QRectF(self._mini.rect()))
            p.restore()
            p.setPen(QPen(estilo.c("borde2"), 1))                    # borde fino: una captura blanca no se pierde
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(caja.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(estilo.VERDE))
            d = 16 if bajo else 20
            ck = (QRectF(caja.right() - d + 4, caja.bottom() - d + 4, d, d) if bajo
                  else QRectF(caja.right() - 12, caja.top() - 6, d, d))
            p.drawEllipse(ck)
            p.setPen(QPen(QColor("white"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(ck.left() + d * 0.27, ck.center().y()), QPointF(ck.left() + d * 0.44, ck.bottom() - d * 0.3),
                            QPointF(ck.right() - d * 0.25, ck.top() + d * 0.32)])
            x = caja.right() + (14 if bajo else 18)
            f.setPixelSize(13 if bajo else 14)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(estilo.c("texto"))
            cy = r.center().y()
            p.drawText(QRectF(x, cy - (20 if bajo else 30), r.right() - x - 10, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       "Captura del pago lista")
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(estilo.c("texto3"))
            if bajo:
                linea = f"{Path(self.ruta).name}  ·  clic para cambiarla"
                p.drawText(QRectF(x, cy + 1, r.right() - x - 10, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(linea, Qt.ElideMiddle, int(r.right() - x - 10)))
            else:
                nombre = p.fontMetrics().elidedText(Path(self.ruta).name, Qt.ElideMiddle, int(r.right() - x - 10))
                p.drawText(QRectF(x, cy - 8, r.right() - x - 10, 18), Qt.AlignLeft | Qt.AlignVCenter, nombre)
                p.drawText(QRectF(x, cy + 10, r.right() - x - 10, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           f"Clic para cambiarla · {CTRL}V para pegar otra")
        elif r.height() < 80:      # recuadro bajo: ícono y texto en un solo renglón
            lado = 22
            color_ico = QColor(estilo.ROJO) if self.error else estilo.c("texto2")
            f.setPixelSize(13)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            titulo = "Falta la captura del pago" if self.error else "Arrastra la captura del pago"
            ayuda = f"  ·  clic para buscarla · {CTRL}V para pegarla"
            ancho_t = p.fontMetrics().horizontalAdvance(titulo)
            g = QFont(f)
            g.setPixelSize(12)
            g.setWeight(QFont.Normal)
            from PySide6.QtGui import QFontMetrics
            ancho_a = QFontMetrics(g).horizontalAdvance(ayuda)
            if lado + 10 + ancho_t + ancho_a > r.width() - 24:
                ayuda, ancho_a = "", 0
            x = r.center().x() - (lado + 10 + ancho_t + ancho_a) / 2
            p.drawPixmap(QPointF(x, r.center().y() - lado / 2), estilo.pixmap_icono("recibo", color_ico, lado))
            x += lado + 10
            p.setPen(QColor(estilo.ROJO) if self.error else estilo.c("texto"))
            p.drawText(QRectF(x, r.top(), ancho_t + 2, r.height()), Qt.AlignLeft | Qt.AlignVCenter, titulo)
            p.setFont(g)
            p.setPen(estilo.c("texto3"))
            p.drawText(QRectF(x + ancho_t, r.top(), ancho_a + 2, r.height()), Qt.AlignLeft | Qt.AlignVCenter, ayuda)
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
        estilo.animar(self, "_ani_mini", 0.0, 1.0, 360, lambda v: self._poner_t("_t_mini", v),
                      QEasingCurve.OutCubic)
        self.cambiada.emit(ruta)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()
            self._arrastre(True)

    def dragLeaveEvent(self, e):
        self._arrastre(False)

    def dropEvent(self, e):
        self._arrastre(False)
        for url in e.mimeData().urls():
            if url.toLocalFile().lower().endswith(EXT_IMAGEN):
                self.usar(url.toLocalFile())
                return


class CampoFecha(QWidget):
    """Fecha fácil y rápida (en vez del calendario, que era lento y obligaba a pasar mes por mes):
    - se escribe de corrido: «20022027» → 20/02/2027 (las barras ya están; al entrar se selecciona todo);
    - ↑ / ↓ (o la rueda del mouse con el campo activo) cambian el día, el mes o el año donde está el cursor;
    - el botón del calendario la elige con el mouse (calendario rápido, se cierra al elegir).
    Misma API que CalendarPicker: getDate(), setDate(), dateChanged (solo con una fecha completa y válida)."""
    dateChanged = Signal(QDate)
    FORMATO = "dd/MM/yyyy"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fecha = QDate.currentDate()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.edit = LineEdit()
        self.edit.setInputMask("99/99/9999")      # con máscara se escribe encima: las barras se saltan solas
        self.edit.setText(self._fecha.toString(self.FORMATO))
        self.edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.edit.textEdited.connect(self._escrito)
        self.edit.editingFinished.connect(self._terminar)
        self.edit.installEventFilter(self)
        self.edit.setToolTip("Escribe la fecha de corrido (día, mes, año) · ↑ ↓ cambian el día, mes o año")
        self.edit.installEventFilter(ToolTipFilter(self.edit))
        h.addWidget(self.edit, 1)
        # el botón del calendario va dentro del campo (como el del buscador): la fecha cabe aunque la
        # columna sea angosta
        self.b_cal = LineEditButton(FIF.CALENDAR, self.edit)
        self.b_cal.setToolTip("Elegir en el calendario")
        self.b_cal.installEventFilter(ToolTipFilter(self.b_cal))
        self.b_cal.clicked.connect(self._calendario)
        self.edit.hBoxLayout.addWidget(self.b_cal, 0, Qt.AlignRight)
        self.edit.setTextMargins(0, 0, 30, 0)
        self.edit.setMinimumWidth(126)

    # ---- API como la de CalendarPicker ----
    def getDate(self):
        return QDate(self._fecha)

    def setDate(self, fecha):
        fecha = QDate(fecha)
        if not fecha.isValid():
            return
        cambio = fecha != self._fecha
        self._fecha = fecha
        if self.edit.text() != fecha.toString(self.FORMATO):
            self.edit.setText(fecha.toString(self.FORMATO))
        self.edit.setError(False)
        if cambio:
            self.dateChanged.emit(QDate(fecha))

    def setDateFormat(self, formato):
        pass   # siempre dd/MM/aaaa

    # ---- edición ----
    def _escrito(self, texto):
        fecha = QDate.fromString(texto, self.FORMATO)
        completo = all(c.isdigit() for c in texto.replace("/", ""))
        self.edit.setError(completo and not fecha.isValid())   # p. ej. 31/02: en rojo hasta corregirla
        if fecha.isValid() and fecha != self._fecha:
            self._fecha = fecha
            self.dateChanged.emit(QDate(fecha))

    def _terminar(self):
        if not QDate.fromString(self.edit.text(), self.FORMATO).isValid():   # incompleta o imposible:
            self.edit.setText(self._fecha.toString(self.FORMATO))           # vuelve la última buena
        self.edit.setError(False)

    def _sumar(self, paso):
        pos = self.edit.cursorPosition()
        f = self._fecha
        f = f.addDays(paso) if pos < 3 else f.addMonths(paso) if pos < 6 else f.addYears(paso)
        self.setDate(f)
        self.edit.setCursorPosition(pos)

    def eventFilter(self, obj, e):
        if obj is self.edit:
            t = e.type()
            if t == QEvent.FocusIn:                          # al entrar: todo seleccionado, se escribe encima
                QTimer.singleShot(0, self.edit.selectAll)
            elif t == QEvent.KeyPress and e.key() in (Qt.Key_Up, Qt.Key_Down):
                self._sumar(1 if e.key() == Qt.Key_Up else -1)
                return True
            elif t == QEvent.Wheel and self.edit.hasFocus():
                pasos = e.angleDelta().y() // 120
                if pasos:
                    self._sumar(1 if pasos > 0 else -1)
                return True
        return super().eventFilter(obj, e)

    def _calendario(self):
        vista = FastCalendarView(self.window())
        vista.setDate(self._fecha)
        flyout = Flyout.make(vista, self.edit, self.window(), FlyoutAnimationType.DROP_DOWN)

        def elegida(d):
            self.setDate(d)
            flyout.close()
        vista.dateChanged.connect(elegida)


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
        self.setFixedHeight(72)
        self.setMinimumWidth(96)
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
        if not angosta:            # el punto rojo crece con un pequeño rebote al elegirla
            t = self._t_sel
            p.setPen(QPen(estilo.mezclar(estilo.c("borde2"), QColor(estilo.ROJO), t), 1.4 + 0.2 * t))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(circ)
            if t > 0.01:
                radio = 4 * min(1.15, t * 1.15) if t < 0.85 else 4 * (1.15 - (t - 0.85))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(estilo.ROJO))
                p.drawEllipse(circ.center(), radio, radio)
        # segundo renglón: precio a la izquierda; servicios (o «MÁS VENDIDO») a la derecha si caben
        fn = estilo.fuente_numeros(20, QFont.Bold, self.font())
        p.setFont(fn)
        p.setPen(estilo.c("texto"))
        fila = QRectF(12 if angosta else 14, 34, w - 24, 28)
        p.drawText(fila, Qt.AlignLeft | Qt.AlignVCenter, q(self.precio))
        libre = w - fila.left() - p.fontMetrics().horizontalAdvance(q(self.precio)) - 22
        if self.destacado:
            f.setPixelSize(9)
            f.setWeight(QFont.Bold)
            p.setFont(f)
            texto = "MÁS VENDIDO" if libre >= 82 else ""      # (sin abreviar: si no cabe, no se pone)
            if texto:
                ancho = p.fontMetrics().horizontalAdvance(texto) + 12
                caja = QRectF(w - ancho - 10, fila.center().y() - 8, ancho, 16)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(estilo.ROJO))
                p.drawRoundedRect(caja, 8, 8)
                p.setPen(QColor("white"))
                p.drawText(caja, Qt.AlignCenter, texto)
        else:
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            texto = f"{self.servicios} servicios" if libre >= 70 else ""
            p.setPen(estilo.c("texto3"))
            p.drawText(QRectF(0, fila.top(), w - 12, fila.height()), Qt.AlignRight | Qt.AlignVCenter, texto)
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
    """Barra fina de cuánto lleva pagado (roja; verde si ya pagó todo). Se llena con movimiento."""

    def __init__(self, pagado=0, total=0, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pagado, self.total = pagado, total
        self._frac = 0.0
        self.setFixedHeight(8)

    def poner(self, pagado, total):
        self.pagado, self.total = pagado, total
        destino = min(pagado / total, 1) if total else 0
        estilo.animar(self, "_ani", 0.0 if self._frac == destino else self._frac, destino, 650,
                      self._paso, QEasingCurve.OutQuart)

    def _paso(self, v):
        self._frac = v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(estilo.c("sup3"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        completo = self.total and self.pagado >= self.total
        p.setBrush(QColor(estilo.VERDE if completo else estilo.ROJO))
        p.drawRoundedRect(QRectF(r.left(), r.top(), max(r.width() * self._frac, r.height()), r.height()),
                          r.height() / 2, r.height() / 2)
        p.end()


def servicio_legible(titulo, detalle=""):
    """Texto de un servicio para la pantalla (el de la plantilla PSD no cambia):
    «Cobertura en» + «(Maquillaje - ceremonia - fiesta)» → «Cobertura», «Maquillaje, ceremonia y fiesta»."""
    titulo = titulo.strip()
    if titulo.lower().endswith(" en"):
        titulo = titulo[:-3]
    detalle = (detalle or "").strip().strip("()").strip()
    partes = [x.strip() for x in detalle.split(" - ") if x.strip()]
    if len(partes) > 1:
        detalle = ", ".join(partes[:-1]) + " y " + partes[-1]
    if detalle:
        detalle = detalle[0].upper() + detalle[1:]
    return titulo, detalle


def etiqueta_estado(estado):
    """Píldora de color para Reservado / Abonado / Pagado."""
    return Pildora(estado, COLOR_ESTADO.get(estado, "#999999"))


class MiniGrafico(QWidget):
    """Gráfico diminuto de una tarjeta de indicador: línea con relleno, barras o puntos de calendario.
    Al recibir datos nuevos se dibuja: la línea avanza, las barras crecen y los puntos aparecen en cascada."""

    def __init__(self, tipo="linea", color=None, parent=None):
        super().__init__(parent)
        self.tipo, self.color = tipo, color
        self.serie = []
        self._p = 1.0
        self.setFixedSize(QSize(70, 40) if tipo == "puntos" else QSize(104, 40))

    def poner(self, serie):
        serie = list(serie or [])
        if serie == self.serie:
            return
        self.serie = serie
        estilo.animar(self, "_ani", 0.0, 1.0, 900 if self.tipo == "puntos" else 750, self._paso,
                      QEasingCurve.OutCubic)

    def _paso(self, v):
        self._p = v
        self.update()

    def paintEvent(self, e):
        if not self.serie:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.color) if self.color else estilo.c("texto2")
        w, h = self.width(), self.height()
        prog = self._p
        if self.tipo == "puntos":      # días del mes: 0 nada, 1 hay evento, 2 hoy
            cols, lado = 7, 6
            n = min(len(self.serie), 35)
            for i, v in enumerate(self.serie[:35]):
                t = max(0.0, min(1.0, prog * 1.6 - i / max(n, 1) * 0.6))     # en cascada
                if t <= 0:
                    continue
                x = (i % cols) * (lado + 4)
                y = (i // cols) * (lado + 2.5)
                col = QColor(estilo.ROJO) if v == 1 else (estilo.c("texto") if v == 2 else estilo.c("sup3"))
                p.setPen(Qt.NoPen)
                p.setBrush(estilo.alfa(col, int(col.alpha() * t)))
                m = lado * (1 - t) / 2
                p.drawEllipse(QRectF(x + m, y + m, lado - 2 * m, lado - 2 * m))
        elif self.tipo == "barras":
            n = len(self.serie)
            maximo = max(self.serie) or 1
            ancho = (w - (n - 1) * 3) / n
            for i, v in enumerate(self.serie):
                t = max(0.0, min(1.0, prog * 1.5 - i * 0.06))
                alto = max(3, (h - 2) * v / maximo) * t
                if alto <= 0:
                    continue
                p.setPen(Qt.NoPen)
                if v == 0:                                       # mes sin comprobantes: apenas una marca
                    p.setBrush(estilo.c("sup3"))
                else:
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
            p.setClipRect(QRectF(0, 0, w * prog, h))          # la línea «se dibuja» de izquierda a derecha
            degr = QLinearGradient(0, 0, 0, h)
            degr.setColorAt(0, estilo.alfa(color, 70))
            degr.setColorAt(1, estilo.alfa(color, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(degr)
            p.drawPath(relleno)
            p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(camino)
            if prog >= 0.98:
                p.setClipping(False)
                p.setPen(Qt.NoPen)
                p.setBrush(estilo.alfa(color, 60))
                p.drawEllipse(pts[-1], 5, 5)
                p.setBrush(color)
                p.drawEllipse(pts[-1], 2.6, 2.6)
        p.end()


class Kpi(Tarjeta):
    """Tarjeta de indicador: ícono en cuadrito, título, cifra grande (cuenta al cambiar) y un mini gráfico."""

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

    def poner_numero(self, valor, formato=str, serie=None):
        self.valor.poner_numero(valor, formato, 700)
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
    Al completarse un paso, su círculo verde aparece con rebote, el ✓ se dibuja y la línea se llena.
    Clic en un paso: elegido(índice). En ventanas angostas solo se ve el nombre del paso actual."""
    elegido = Signal(int)

    def __init__(self, titulos, parent=None):
        super().__init__(parent)
        self.titulos = list(titulos)
        self.completos = [False] * len(self.titulos)
        self._t = [0.0] * len(self.titulos)     # 0 → 1: avance de la animación de «listo» de cada paso
        self._cajas = []
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)

    def poner(self, completos):
        completos = list(completos)
        for i, (antes, ahora) in enumerate(zip(self.completos, completos)):
            if ahora and not antes:
                estilo.animar(self, f"_ani{i}", 0.0, 1.0, 520,
                              lambda v, i=i: self._paso(i, v), QEasingCurve.OutCubic)
            elif not ahora:
                getattr(self, f"_ani{i}", None) and getattr(self, f"_ani{i}").stop()
                self._t[i] = 0.0
        self.completos = completos
        self.update()

    def _paso(self, i, v):
        self._t[i] = v
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
                tt = self._t[i] if hasattr(self, f"_ani{i}") else 1.0
                # rebote: crece de 0.55 a 1.15 y se asienta en 1.0
                esc = 0.55 + tt / 0.6 * 0.6 if tt < 0.6 else 1.15 - 0.15 * (tt - 0.6) / 0.4
                if tt < 1:                                     # halo que se expande y se apaga
                    p.setBrush(estilo.alfa(estilo.VERDE, int(90 * (1 - tt))))
                    p.drawEllipse(circ.center(), d / 2 + 8 * tt, d / 2 + 8 * tt)
                p.setBrush(QColor(estilo.VERDE))
                p.drawEllipse(circ.center(), d / 2 * esc, d / 2 * esc)
                trazo = max(0.0, min(1.0, (tt - 0.3) / 0.55))  # el ✓ se dibuja de a poco
                if trazo > 0:
                    a = QPointF(circ.left() + 5.5, cy)
                    b = QPointF(circ.left() + 8.6, cy + 3.2)
                    c_ = QPointF(circ.right() - 5, cy - 3.6)
                    p.setPen(QPen(QColor("white"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    if trazo < 0.4:
                        k = trazo / 0.4
                        p.drawLine(a, a + (b - a) * k)
                    else:
                        k = (trazo - 0.4) / 0.6
                        p.drawPolyline([a, b, b + (c_ - b) * k])
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
                x0, x1 = x + 8, x + unir - 8
                p.setPen(QPen(estilo.c("borde2"), 1.4))
                p.drawLine(QPointF(x0, cy), QPointF(x1, cy))
                if ok and self.completos[i + 1]:                # verde solo si los dos pasos que une están listos
                    tt = min(self._t[i] if hasattr(self, f"_ani{i}") else 1.0,
                             self._t[i + 1] if hasattr(self, f"_ani{i + 1}") else 1.0)
                    p.setPen(QPen(QColor(estilo.VERDE), 1.6))
                    p.drawLine(QPointF(x0, cy), QPointF(x0 + (x1 - x0) * tt, cy))
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
        v = self.v_bloque = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 18, 14)
        v.setSpacing(10)
        self.cab = _Cabecera()
        h = self.h_cab = QHBoxLayout(self.cab)
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
        self.cuerpo.setSpacing(8)
        v.addWidget(self.contenido)

    def apretar(self, si):
        """Menos aire (ventanas bajas, para que todo quepa sin desplazarse)."""
        self.v_bloque.setContentsMargins(*((16, 9, 16, 10) if si else (18, 12, 18, 14)))
        self.v_bloque.setSpacing(7 if si else 10)

    def en_cabecera(self, w):
        """Pone un control en la cabecera, antes de la píldora de estado (ahorra un renglón)."""
        self.h_cab.insertWidget(self.h_cab.count() - 1, w, 0, Qt.AlignVCenter)

    def abrir(self, si):
        self.resaltar(si and not self.completo)

    def poner_estado(self, completo, resumen, falta=None):
        self.completo = completo
        self.resumen.setText(resumen)
        self.setToolTip(resumen)
        if completo:
            self.estado.poner("Listo", estilo.VERDE)
            self.resaltar(False)
        else:
            verbo = "Faltan " if falta and falta[0].isdigit() else "Falta "
            self.estado.poner((verbo + falta) if falta else "Pendiente", estilo.AMBAR if falta else None)
        self.update()
