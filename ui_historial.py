"""Pantalla «Clientes»: historial, saldos pendientes y registro de abonos."""
import calendar
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QHBoxLayout, QHeaderView, QLabel, QListWidgetItem,
                               QStyle, QStyledItemDelegate, QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (CalendarPicker, CaptionLabel, FlowLayout, FluentIcon as FIF,
                            IndeterminateProgressRing, ListItemDelegate, ListWidget, MessageBox, PrimaryPushButton, PushButton,
                            SearchLineEdit, SmoothScrollArea, StrongBodyLabel, SubtitleLabel,
                            TableItemDelegate, TableWidget, TitleLabel, TransparentPushButton)

import estilo
import motor
import registro
import rutas
from estilo import Cifra, Icono, Pildora, Separador, Tarjeta
from ui_comun import (CTRL, COLOR_ESTADO, COLOR_PAQUETE, Avatar, BarraPago, Kpi, Monto, NOMBRES_PAQUETE, Rejilla,
                      Trabajo, ZonaCaptura, abrir, abrir_whatsapp, aviso, color_avatar, copiar_imagen, faltan,
                      iniciales, q)

COLUMNAS = ["Cliente", "Evento", "Paquete", "Saldo", "Estado"]
COL_FECHA, COL_PAQUETE, COL_SALDO, COL_ESTADO = 1, 2, 3, 4
ANCHOS = {1: 140, 2: 112, 3: 96, 4: 124}
DATOS = Qt.UserRole + 1
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fecha_corta(d):
    return f"{d.day} {MESES_CORTOS[d.month - 1]} {d.year}"


class DelegadoClientes(TableItemDelegate):
    """Pinta cada celda: avatar + nombre + tipo de evento, fecha + días que faltan, paquete con su color,
    saldo (rojo si debe) y la píldora de estado. La fila elegida lleva una franja roja a la izquierda."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)          # fondo de fila (pasar el mouse / elegida)
        dato = index.data(DATOS)
        if dato is None:
            return
        r = QRectF(option.rect)
        cy = r.center().y()
        p = painter
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        col = index.column()
        f = QFont(option.font)
        if col == 0:
            nombre, evento = dato
            if option.state & QStyle.State_Selected:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(estilo.ROJO))
                p.drawRoundedRect(QRectF(r.left() + 2, r.top() + 12, 3, r.height() - 24), 1.5, 1.5)
            d = 34
            caja = QRectF(r.left() + 16, cy - d / 2, d, d)
            p.setPen(Qt.NoPen)
            p.setBrush(color_avatar(nombre))
            p.drawEllipse(caja)
            f.setPixelSize(12)
            f.setWeight(QFont.Bold)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(caja, int(Qt.AlignCenter), iniciales(nombre))
            x = caja.right() + 12
            f.setPixelSize(14)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(estilo.c("texto"))
            p.drawText(QRectF(x, cy - 19, r.right() - x - 8, 20), int(Qt.AlignLeft | Qt.AlignVCenter),
                       p.fontMetrics().elidedText(nombre, Qt.ElideRight, int(r.right() - x - 8)))
            f.setPixelSize(12)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(estilo.c("texto3"))
            p.drawText(QRectF(x, cy + 1, r.right() - x - 8, 18), int(Qt.AlignLeft | Qt.AlignVCenter), evento)
        elif col == COL_FECHA:
            fecha = dato
            p.drawPixmap(QPointF(r.left() + 12, cy - 17), estilo.pixmap_icono("calendario", estilo.c("texto3"), 14))
            f.setPixelSize(13)
            p.setFont(f)
            p.setPen(estilo.c("texto"))
            p.drawText(QRectF(r.left() + 32, cy - 20, r.width() - 36, 20), int(Qt.AlignLeft | Qt.AlignVCenter),
                       _fecha_corta(fecha))
            f.setPixelSize(12)
            p.setFont(f)
            p.setPen(estilo.c("texto3"))
            p.drawText(QRectF(r.left() + 32, cy, r.width() - 36, 18), int(Qt.AlignLeft | Qt.AlignVCenter),
                       faltan(fecha))
        elif col == COL_PAQUETE:
            clave = dato
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLOR_PAQUETE.get(clave, "#888")))
            p.drawEllipse(QRectF(r.left() + 12, cy - 3.5, 7, 7))
            f.setPixelSize(13)
            p.setFont(f)
            p.setPen(estilo.c("texto"))
            p.drawText(QRectF(r.left() + 26, r.top(), r.width() - 30, r.height()), int(Qt.AlignLeft | Qt.AlignVCenter),
                       NOMBRES_PAQUETE.get(clave, clave.title()))
        elif col == COL_SALDO:
            saldo = dato
            p.setFont(estilo.fuente_numeros(14, QFont.Bold if saldo > 0 else QFont.Normal, option.font))
            p.setPen(QColor(estilo.ROJO_CLARO) if saldo > 0 else estilo.c("texto3"))
            p.drawText(QRectF(r.left() + 8, r.top(), r.width() - 20, r.height()), int(Qt.AlignRight | Qt.AlignVCenter),
                       q(saldo))
        elif col == COL_ESTADO:
            estado = dato
            color = QColor(COLOR_ESTADO.get(estado, "#999999"))
            f.setPixelSize(12)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            ancho = p.fontMetrics().horizontalAdvance(estado) + 34
            caja = QRectF(r.left() + 12, cy - 12, ancho, 24)
            p.setPen(QPen(estilo.alfa(color, 70), 1))
            p.setBrush(estilo.alfa(color, 34))
            p.drawRoundedRect(caja, 12, 12)
            punto = QPointF(caja.left() + 13, cy)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(punto, 3.2, 3.2)
            p.setPen(color)
            p.drawText(caja.adjusted(22, 0, -8, 0), int(Qt.AlignLeft | Qt.AlignVCenter), estado)
        p.restore()


class DelegadoPagos(ListItemDelegate):
    """Historial de pagos como línea de tiempo: punto, fecha · concepto y el monto a la derecha."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 50)

    def paint(self, p, option, index):
        fecha, concepto, monto, primero, ultimo = index.data(DATOS)
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        elegido = bool(option.state & QStyle.State_Selected)
        if elegido or option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(estilo.alfa(estilo.ROJO, 28) if elegido else estilo.c("sup3"))
            p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 8, 8)
        x = r.left() + 16
        p.setPen(QPen(estilo.c("borde2"), 1.4))
        if not primero:
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.center().y() - 7))
        if not ultimo:
            p.drawLine(QPointF(x, r.center().y() + 7), QPointF(x, r.bottom()))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(estilo.VERDE))
        p.drawEllipse(QPointF(x, r.center().y()), 5, 5)
        f = QFont(option.font)
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(estilo.c("texto"))
        p.drawText(QRectF(x + 16, r.top() + 6, r.width() - 120, 20), int(Qt.AlignLeft | Qt.AlignVCenter), concepto)
        f.setPixelSize(12)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(estilo.c("texto3"))
        p.drawText(QRectF(x + 16, r.top() + 25, r.width() - 120, 18), int(Qt.AlignLeft | Qt.AlignVCenter),
                   _fecha_corta(fecha))
        p.setFont(estilo.fuente_numeros(14, QFont.Bold, option.font))
        p.setPen(estilo.c("texto"))
        p.drawText(QRectF(r.left(), r.top(), r.width() - 14, r.height()), int(Qt.AlignRight | Qt.AlignVCenter),
                   q(monto))
        p.restore()


class ChipFiltro(QWidget):
    """Filtro en píldora con su conteo («Reservado 5»). El activo va en rojo suave."""
    clicked = Signal()

    def __init__(self, texto, parent=None):
        super().__init__(parent)
        self.texto, self.n, self.activo = texto, 0, False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self._medir()

    def _fuente(self):
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        return f

    def _medir(self):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self._fuente())
        self.setFixedWidth(fm.horizontalAdvance(self.texto) + fm.horizontalAdvance(str(self.n)) + 36)

    def poner(self, n=None, activo=None):
        if n is not None:
            self.n = n
        if activo is not None:
            self.activo = activo
        self._medir()
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.activo:
            p.setPen(QPen(estilo.alfa(estilo.ROJO, 150), 1))
            p.setBrush(estilo.alfa(estilo.ROJO, 40))
        else:
            p.setPen(QPen(estilo.c("borde"), 1))
            p.setBrush(estilo.c("sup"))
        p.drawRoundedRect(r, 10, 10)
        p.setFont(self._fuente())
        fm = p.fontMetrics()
        p.setPen(estilo.c("texto") if self.activo else estilo.c("texto2"))
        p.drawText(QRectF(13, 0, self.width(), self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.texto)
        p.setPen(QColor(estilo.ROJO_CLARO) if self.activo else estilo.c("texto3"))
        p.drawText(QRectF(13 + fm.horizontalAdvance(self.texto) + 8, 0, 40, self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, str(self.n))
        p.end()


class _Ilustracion(QLabel):
    """La ilustración de «aún no hay clientes» (Higgsfield), escalada a su caja."""

    def __init__(self, ancho, parent=None):
        super().__init__(parent)
        pm = QPixmap(str(rutas.recurso("recursos/ilustracion_vacio.png")))
        if not pm.isNull():
            dpr = self.devicePixelRatioF() or 2
            pm = pm.scaledToWidth(int(ancho * dpr), Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            self.setPixmap(pm)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:transparent")


class HistorialInterface(QWidget):
    pedir_nuevo = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("historial")
        self.cfg = cfg
        self.clientes = []
        self.actual = None
        self.trabajo = None
        self.filtro = "Todos"

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        izq = self.izq = QWidget()
        v = self.v_izq = QVBoxLayout(izq)
        v.setContentsMargins(32, 24, 20, 20)
        v.setSpacing(14)
        cab = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(2)
        tit.addWidget(TitleLabel("Clientes y pagos"))
        sub = CaptionLabel("Saldos pendientes, abonos y comprobantes de cada cliente")
        sub.setWordWrap(True)
        tit.addWidget(sub)
        cab.addLayout(tit, 1)
        self.b_nuevo = PrimaryPushButton(FIF.ADD, "Nuevo comprobante")
        self.b_nuevo.setFixedHeight(38)
        self.b_nuevo.clicked.connect(lambda: self.pedir_nuevo.emit())
        cab.addWidget(self.b_nuevo, 0, Qt.AlignVCenter)
        v.addLayout(cab)

        self.k_cobrar = Kpi("Por cobrar", estilo.ROJO, "recibo", "linea")
        self.k_mes = Kpi("Eventos este mes", None, "calendario", "puntos")
        self.k_comp = Kpi("Comprobantes", estilo.VERDE, "carpeta", "barras")
        self.k_cobrar.setToolTip("Saldo pendiente de todos los clientes · gráfico: por mes del evento")
        self.k_mes.setToolTip("Eventos de este mes · cada punto es un día (rojo = hay evento)")
        self.k_comp.setToolTip("Comprobantes generados · barras: los últimos 8 meses")
        v.addWidget(Rejilla([self.k_cobrar, self.k_mes, self.k_comp], max_columnas=3, ancho_min=150))

        self.buscar = SearchLineEdit()
        self.buscar.setPlaceholderText(f"Buscar por nombre, teléfono, paquete o lugar…   {CTRL}F")
        self.buscar.textChanged.connect(self.refrescar)
        self.chips = {}
        fila_chips = QWidget()
        hc = QHBoxLayout(fila_chips)
        hc.setContentsMargins(0, 0, 0, 0)
        hc.setSpacing(8)
        for nombre in ("Todos", "Reservado", "Abonado", "Pagado"):
            chip = ChipFiltro(nombre)
            chip.clicked.connect(lambda n=nombre: self._filtrar(n))
            self.chips[nombre] = chip
            hc.addWidget(chip)
        hc.addStretch(1)
        self.fila_b = QBoxLayout(QBoxLayout.LeftToRight)       # en ventanas angostas, los filtros bajan
        self.fila_b.setSpacing(12)
        self.fila_b.addWidget(self.buscar, 1)
        self.fila_b.addWidget(fila_chips)
        v.addLayout(self.fila_b)

        self.marco_tabla = Tarjeta()
        mt = QVBoxLayout(self.marco_tabla)
        mt.setContentsMargins(6, 6, 6, 6)
        self.tabla = TableWidget()
        self.tabla.setBorderVisible(False)
        self.tabla.setWordWrap(False)
        self.tabla.setShowGrid(False)
        self.tabla.setColumnCount(len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setItemDelegate(DelegadoClientes(self.tabla))
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(64)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        h = self.tabla.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        h.setSectionResizeMode(QHeaderView.Fixed)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, ancho in ANCHOS.items():
            self.tabla.setColumnWidth(col, ancho)
        h.setMinimumSectionSize(60)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        mt.addWidget(self.tabla)
        v.addWidget(self.marco_tabla, 1)

        self.vacio = QWidget()
        ve = QVBoxLayout(self.vacio)
        ve.setSpacing(10)
        ve.addStretch(1)
        ve.addWidget(_Ilustracion(300), 0, Qt.AlignHCenter)
        ve.addWidget(SubtitleLabel("Aquí aparecerán tus clientes"), 0, Qt.AlignHCenter)
        ve.addWidget(CaptionLabel("Cada comprobante que generes queda guardado con su saldo y sus abonos."),
                     0, Qt.AlignHCenter)
        ve.addSpacing(4)
        b_primero = PrimaryPushButton(FIF.ADD, "Crear el primer comprobante")
        b_primero.clicked.connect(lambda: self.pedir_nuevo.emit())
        ve.addWidget(b_primero, 0, Qt.AlignHCenter)
        ve.addStretch(2)
        v.addWidget(self.vacio, 1)
        raiz.addWidget(izq, 1)

        # ---------- Panel de detalle ----------
        self.panel = Tarjeta(radio=16)
        self.panel.setFixedWidth(372)
        marco = QVBoxLayout()
        marco.setContentsMargins(0, 20, 20, 20)
        marco.addWidget(self.panel)
        scroll = SmoothScrollArea(self.panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(scroll)
        p = self.p_panel = QVBoxLayout(cont)
        p.setContentsMargins(20, 22, 20, 18)
        p.setSpacing(10)
        cabd = QHBoxLayout()
        cabd.setSpacing(14)
        self.d_avatar = Avatar("?", 54)
        cabd.addWidget(self.d_avatar, 0, Qt.AlignTop)
        tv = QVBoxLayout()
        tv.setSpacing(4)
        self.d_nombre = SubtitleLabel("Selecciona un cliente")
        self.d_nombre.setWordWrap(True)
        tv.addWidget(self.d_nombre)
        self.d_chips = QWidget()
        self.flow = FlowLayout(self.d_chips, needAni=False)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setHorizontalSpacing(6)
        self.flow.setVerticalSpacing(6)
        tv.addWidget(self.d_chips)
        cabd.addLayout(tv, 1)
        p.addLayout(cabd)
        self.d_info = CaptionLabel("")
        self.d_info.setWordWrap(True)
        p.addWidget(self.d_info)
        p.addSpacing(4)
        self.d_progreso = CaptionLabel("")
        p.addWidget(self.d_progreso)
        self.d_barra = BarraPago()
        p.addWidget(self.d_barra)
        self.caja_saldo = Tarjeta(nivel=2, radio=12)
        cs = QVBoxLayout(self.caja_saldo)
        cs.setContentsMargins(16, 12, 16, 12)
        cs.setSpacing(0)
        cs.addWidget(CaptionLabel("Saldo pendiente"))
        self.d_saldo = Cifra("—", 26, estilo.ROJO)
        cs.addWidget(self.d_saldo)
        p.addWidget(self.caja_saldo)

        p.addSpacing(6)
        p.addWidget(StrongBodyLabel("Historial de pagos"))
        self.lista = ListWidget()
        self.lista.setItemDelegate(DelegadoPagos(self.lista))
        self.lista.setFixedHeight(156)
        self.lista.itemDoubleClicked.connect(lambda it: abrir(it.data(Qt.UserRole)))
        p.addWidget(self.lista)
        self.b_ver = PushButton(FIF.VIEW, "Ver")
        self.b_ver.setToolTip("Abrir el comprobante elegido")
        self.b_ver.clicked.connect(self._abrir_pago)
        self.b_copiar = PushButton(FIF.COPY, "Copiar")
        self.b_copiar.clicked.connect(self._copiar_pago)
        self.b_wa = PushButton(FIF.CHAT.icon(color=QColor(estilo.VERDE)), "WhatsApp")
        self.b_wa.clicked.connect(self._whatsapp)
        p.addWidget(Rejilla([self.b_ver, self.b_copiar, self.b_wa], max_columnas=3, ancho_min=90, espacio=8))
        p.addWidget(Separador())

        self.t_abono = StrongBodyLabel("Registrar abono")
        p.addWidget(self.t_abono)
        self.caja_abono = QWidget()
        a = QVBoxLayout(self.caja_abono)
        a.setContentsMargins(0, 0, 0, 0)
        a.setSpacing(8)
        self.monto = Monto()
        self.fecha = CalendarPicker()
        self.fecha.setDateFormat("dd/MM/yyyy")
        self.fecha.setDate(QDate.currentDate())
        a.addWidget(Rejilla([self.monto, self.fecha], max_columnas=2, ancho_min=120, espacio=8))
        self.zona = ZonaCaptura(104)
        a.addWidget(self.zona)
        fila_z = QHBoxLayout()
        b_pegar = TransparentPushButton(FIF.PASTE, f"Pegar captura ({CTRL}V)")
        b_pegar.clicked.connect(self.zona.pegar)
        self.ring = IndeterminateProgressRing()
        self.ring.setFixedSize(22, 22)
        self.ring.hide()
        fila_z.addWidget(b_pegar)
        fila_z.addStretch(1)
        fila_z.addWidget(self.ring)
        a.addLayout(fila_z)
        self.b_abono = PrimaryPushButton(FIF.ACCEPT, "Registrar abono")
        self.b_abono.setToolTip(f"Genera el comprobante del abono ({CTRL}Enter)")
        self.b_abono.setFixedHeight(40)
        self.b_abono.clicked.connect(self.generar_abono)
        a.addWidget(self.b_abono)
        p.addWidget(self.caja_abono)
        self.pagado_ok = Pildora("Este cliente ya pagó todo", estilo.VERDE, alto=30, tam_letra=13)
        p.addWidget(self.pagado_ok)
        p.addStretch(1)
        self.b_borrar = TransparentPushButton(FIF.DELETE.icon(color=QColor(estilo.ROJO_CLARO)), "Eliminar cliente")
        self.b_borrar.clicked.connect(self.eliminar)
        p.addWidget(self.b_borrar, 0, Qt.AlignHCenter)
        raiz.addLayout(marco)

        self._detalle(None)
        self.refrescar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ancho = self.width()
        # el panel de detalle se angosta en ventanas chicas (laptops, MacBook)
        self.panel.setFixedWidth(372 if ancho >= 1100 else (320 if ancho >= 900 else 286))
        chico = ancho < 900
        self.v_izq.setContentsMargins(*((18, 16, 14, 14) if chico else (32, 24, 20, 20)))
        self.p_panel.setContentsMargins(*((14, 18, 14, 14) if chico else (20, 22, 20, 18)))
        self.b_nuevo.setText("Nuevo" if ancho - self.panel.width() < 600 else "Nuevo comprobante")
        self.fila_b.setDirection(QBoxLayout.TopToBottom if ancho - self.panel.width() < 760 else QBoxLayout.LeftToRight)
        QTimer.singleShot(0, self._columnas)

    def _columnas(self):
        # Si la tabla queda angosta se ocultan columnas (el detalle las sigue mostrando),
        # para que el nombre del cliente, el saldo y el estado siempre se lean.
        ancho = self.tabla.viewport().width()
        self.tabla.setColumnHidden(COL_PAQUETE, ancho < 600)
        self.tabla.setColumnHidden(COL_FECHA, ancho < 480)

    # ---------- datos ----------
    def showEvent(self, e):
        super().showEvent(e)
        self.refrescar()
        QTimer.singleShot(0, self._columnas)

    def _series(self, todos):
        """Datos de los mini gráficos: saldo por mes del evento (6 meses), días con evento este mes y
        comprobantes de los últimos 8 meses."""
        hoy = date.today()

        def mes_mas(n):
            m = hoy.month - 1 + n
            return hoy.year + m // 12, m % 12 + 1
        meses = [mes_mas(i) for i in range(6)]
        cobrar = [sum(c.saldo for c in todos if (c.fecha_evento.year, c.fecha_evento.month) == m) for m in meses]
        dias = calendar.monthrange(hoy.year, hoy.month)[1]
        con_evento = {c.fecha_evento.day for c in todos
                      if c.fecha_evento.year == hoy.year and c.fecha_evento.month == hoy.month}
        puntos = [1 if d in con_evento else (2 if d == hoy.day else 0) for d in range(1, dias + 1)]
        atras = [mes_mas(i) for i in range(-7, 1)]
        cuenta = {m: 0 for m in atras}
        for c in todos:
            for _, fecha, *_ in registro.pagos(c.id):
                d = date.fromisoformat(fecha)
                if (d.year, d.month) in cuenta:
                    cuenta[(d.year, d.month)] += 1
        return cobrar, puntos, [cuenta[m] for m in atras]

    def refrescar(self):
        r = registro.resumen()
        todos = registro.clientes("")
        cobrar, puntos, comprobantes = self._series(todos)
        self.k_cobrar.poner(q(r["por_cobrar"]), cobrar)
        self.k_mes.poner(str(r["eventos_mes"]), puntos)
        self.k_comp.poner(str(r["comprobantes"]), comprobantes)
        buscados = registro.clientes(self.buscar.text())
        for nombre, chip in self.chips.items():
            chip.poner(n=len(buscados) if nombre == "Todos" else sum(c.estado == nombre for c in buscados),
                       activo=nombre == self.filtro)
        seleccion = self.actual.id if self.actual else None
        self.clientes = [c for c in buscados if self.filtro == "Todos" or c.estado == self.filtro]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self.clientes))
        fila_sel = -1
        for f, c in enumerate(self.clientes):
            for col in range(len(COLUMNAS)):
                self.tabla.setItem(f, col, QTableWidgetItem(""))
            self.tabla.item(f, 0).setData(DATOS, (c.festejado, c.evento))
            self.tabla.item(f, 0).setToolTip(f"{c.festejado} · {c.telefono}")
            self.tabla.item(f, COL_FECHA).setData(DATOS, c.fecha_evento)
            self.tabla.item(f, COL_PAQUETE).setData(DATOS, c.paquete)
            self.tabla.item(f, COL_SALDO).setData(DATOS, c.saldo)
            self.tabla.item(f, COL_ESTADO).setData(DATOS, c.estado)
            self.tabla.setRowHeight(f, 64)
            if c.id == seleccion:
                fila_sel = f
        self.tabla.blockSignals(False)
        vacio = not todos
        self.vacio.setVisible(vacio)
        self.marco_tabla.setVisible(not vacio)
        if fila_sel >= 0:
            self.tabla.selectRow(fila_sel)
            self._detalle(registro.cliente(seleccion))
        else:
            self._detalle(None)

    def _filtrar(self, nombre):
        self.filtro = nombre
        self.refrescar()

    def _seleccion(self):
        filas = self.tabla.selectionModel().selectedRows()
        self._detalle(self.clientes[filas[0].row()] if filas else None)

    def _detalle(self, c):
        self.actual = c
        hay = c is not None
        for w in (self.b_ver, self.b_copiar, self.b_wa, self.b_borrar, self.lista):
            w.setEnabled(hay)
        for w in (self.d_avatar, self.d_barra, self.d_progreso, self.caja_saldo, self.d_chips):
            w.setVisible(hay)
        self.flow.takeAllWidgets()
        if not hay:
            self.d_nombre.setText("Selecciona un cliente")
            self.d_info.setText("Elige una fila de la tabla para ver sus pagos y registrar abonos.")
            self.lista.clear()
            self.caja_abono.setVisible(False)
            self.t_abono.setVisible(False)
            self.pagado_ok.setVisible(False)
            return
        self.d_nombre.setText(c.festejado)
        self.d_avatar.poner(c.festejado)
        for texto, color in ((c.evento, None), (NOMBRES_PAQUETE.get(c.paquete, c.paquete), COLOR_PAQUETE.get(c.paquete)),
                             (c.fecha_evento.strftime("%d/%m/%Y"), None), (faltan(c.fecha_evento), None)):
            self.flow.addWidget(Pildora(texto, color, tam_letra=11, alto=22))
        self.d_info.setText(" · ".join(x for x in (c.lugar, c.telefono) if x))
        porcentaje = int(100 * c.pagado / c.total) if c.total else 0
        self.d_progreso.setText(f"{q(c.pagado)} de {q(c.total)} pagado ({porcentaje}%)")
        self.d_barra.poner(c.pagado, c.total)
        self.d_saldo.setText(q(c.saldo))
        self.d_saldo.poner_color(estilo.ROJO if c.saldo > 0 else estilo.VERDE)
        self.lista.clear()
        pagos = registro.pagos(c.id)
        for i, (_, fecha, monto, concepto, comprobante) in enumerate(pagos):
            it = QListWidgetItem()
            it.setData(Qt.UserRole, comprobante)
            it.setData(DATOS, (date.fromisoformat(fecha), concepto, monto, i == 0, i == len(pagos) - 1))
            it.setToolTip("Doble clic para abrir el comprobante")
            self.lista.addItem(it)
        if self.lista.count():
            self.lista.setCurrentRow(self.lista.count() - 1)
        debe = c.saldo > 0
        self.caja_abono.setVisible(debe)
        self.t_abono.setVisible(debe)
        self.pagado_ok.setVisible(not debe)
        if debe:
            self.monto.setValue(int(c.saldo))
            self.fecha.setDate(QDate.currentDate())
            self.zona.limpiar()

    def _pago_actual(self):
        it = self.lista.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _abrir_pago(self):
        ruta = self._pago_actual()
        if ruta and Path(ruta).exists():
            abrir(ruta)
        else:
            aviso(self, "warning", "No encontrado", "Ese comprobante se movió o se borró de la carpeta.")

    def _copiar_pago(self):
        ruta = self._pago_actual()
        if ruta and Path(ruta).exists():
            copiar_imagen(ruta)
            aviso(self, "success", "Copiado", f"Pégalo en WhatsApp con {CTRL}V.")

    def _whatsapp(self):
        c = self.actual
        ruta = self._pago_actual()
        if not c:
            return
        if ruta and Path(ruta).exists():
            copiar_imagen(ruta)
        if abrir_whatsapp(c.telefono, c.festejado):
            aviso(self, "success", "WhatsApp", f"Se abrió el chat del cliente. Pega el comprobante con {CTRL}V.", 6000)
        else:
            aviso(self, "warning", "Teléfono", "Este cliente no tiene un teléfono válido.")

    # ---------- acciones ----------
    def generar_abono(self):
        c = self.actual
        if not c:
            return
        monto = self.monto.value()
        if monto <= 0:
            aviso(self, "warning", "Monto", "Escribe el monto del abono.")
            return
        if monto > c.saldo:
            aviso(self, "warning", "Monto", f"El abono es mayor que el saldo pendiente ({q(c.saldo)}).")
            return
        if not self.zona.ruta:
            self.zona.marcar_error(True)
            aviso(self, "warning", "Falta la captura", "Sube o pega la captura del abono.")
            return
        saldo = c.saldo - monto
        self.datos = dict(evento=c.evento, paquete=c.paquete, festejado=c.festejado, lugar=c.lugar,
                          fecha_evento=c.fecha_evento, fecha_comprobante=self.fecha.getDate().toPython(),
                          contacto=c.telefono, total=c.total, monto=monto, saldo=saldo,
                          concepto="PAGO FINAL" if saldo <= 0 else "ABONO", captura=self.zona.ruta)
        self.b_abono.setEnabled(False)
        self.b_abono.setText("Generando…")
        self.ring.show()
        self.trabajo = Trabajo(self.datos, self.cfg)
        self.trabajo.listo.connect(self._listo)
        self.trabajo.fallo.connect(self._fallo)
        self.trabajo.start()

    def _fin(self):
        self.b_abono.setEnabled(True)
        self.b_abono.setText("Registrar abono")
        self.ring.hide()

    def _listo(self, ruta):
        self._fin()
        d = self.datos
        registro.agregar_pago(self.actual.id, d["fecha_comprobante"], d["monto"],
                              motor.CONCEPTOS[d["concepto"]].title(), ruta)
        copiar_imagen(ruta)
        self.refrescar()
        aviso(self, "success", "Abono registrado",
              f"Saldo: {q(d['saldo'])}. Comprobante copiado: pégalo en WhatsApp con {CTRL}V.", 7000,
              ruta_abrir=ruta)

    def _fallo(self, msg):
        self._fin()
        aviso(self, "error", "Error", msg, 10000)

    def eliminar(self):
        c = self.actual
        if not c:
            return
        caja = MessageBox("Eliminar cliente",
                          f"¿Eliminar a «{c.festejado}» y sus pagos del historial?\n"
                          "Los comprobantes (JPG) ya generados no se borran.", self.window())
        caja.yesButton.setText("Eliminar")
        caja.cancelButton.setText("Cancelar")
        if caja.exec():
            registro.eliminar_cliente(c.id)
            self.actual = None
            self.refrescar()
