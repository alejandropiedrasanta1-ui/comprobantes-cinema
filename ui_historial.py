"""Pantalla «Clientes»: historial, saldos pendientes y registro de abonos."""
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QHBoxLayout, QHeaderView, QListWidgetItem,
                               QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CalendarPicker, CaptionLabel, FluentIcon as FIF,
                            HorizontalSeparator, IconWidget, IndeterminateProgressRing, ListWidget,
                            MessageBox, PrimaryPushButton, ProgressBar, PushButton, SearchLineEdit,
                            SegmentedWidget,
                            SimpleCardWidget, SmoothScrollArea, StrongBodyLabel, SubtitleLabel,
                            TableItemDelegate, TableWidget, TitleLabel, TransparentPushButton,
                            isDarkTheme)

import motor
import registro
from ui_comun import (CTRL, COLOR_ESTADO, COLORES_AVATAR, Avatar, Kpi, Monto, NOMBRES_PAQUETE, Rejilla,
                      Trabajo, ZonaCaptura, abrir, abrir_whatsapp, aviso, copiar_imagen, etiqueta_valor, faltan, iniciales, q)

COLUMNAS = ["Cliente", "Fecha", "Paquete", "Pagado", "Saldo", "Estado"]
COL_FECHA, COL_PAQUETE, COL_PAGADO, COL_ESTADO = 1, 2, 3, 5
ANCHOS = {1: 118, 2: 155, 3: 160, 4: 90, 5: 115}


DATOS = Qt.UserRole + 1


class DelegadoClientes(TableItemDelegate):
    """Dibuja dentro de la celda (alineado con el texto de la fila): iniciales + nombre,
    «Q600 de Q1,500» con barra de pago, y la etiqueta de estado."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        dato = index.data(DATOS)
        if dato is None:
            return
        r = QRectF(option.rect)
        cy = r.center().y()
        oscuro = isDarkTheme()
        p = painter
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        col = index.column()
        if col == 0:
            nombre = dato
            d = 30
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLORES_AVATAR[sum(map(ord, nombre)) % len(COLORES_AVATAR)]))
            p.drawEllipse(QRectF(r.left() + 12, cy - d / 2, d, d))
            f = QFont(option.font)
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(r.left() + 12, cy - d / 2, d, d), int(Qt.AlignCenter), iniciales(nombre))
            f.setBold(False)
            f.setPixelSize(14)
            p.setFont(f)
            p.setPen(QColor("white") if oscuro else QColor("black"))
            p.drawText(QRectF(r.left() + 52, r.top(), r.width() - 60, r.height()),
                       int(Qt.AlignLeft | Qt.AlignVCenter), nombre)
        elif col == COL_PAGADO:
            pagado, total = dato
            f = QFont(option.font)
            f.setPixelSize(12)
            p.setFont(f)
            p.setPen(QColor("#c8c8cd") if oscuro else QColor("#444"))
            p.drawText(QRectF(r.left() + 12, cy - 16, r.width() - 24, 16),
                       int(Qt.AlignLeft | Qt.AlignVCenter), f"{q(pagado)} de {q(total)}")
            ancho = r.width() - 24
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 30) if oscuro else QColor(0, 0, 0, 25))
            p.drawRoundedRect(QRectF(r.left() + 12, cy + 4, ancho, 4), 2, 2)
            frac = min(pagado / total, 1) if total else 0
            p.setBrush(QColor("#52be80") if frac >= 1 else QColor("#e0262b"))
            p.drawRoundedRect(QRectF(r.left() + 12, cy + 4, max(ancho * frac, 4), 4), 2, 2)
        elif col == COL_ESTADO:
            estado = dato
            color = QColor(COLOR_ESTADO.get(estado, "#999999"))
            f = QFont(option.font)
            f.setPixelSize(12)
            f.setBold(True)
            p.setFont(f)
            ancho = p.fontMetrics().horizontalAdvance(estado) + 22
            caja = QRectF(r.center().x() - ancho / 2, cy - 11, ancho, 22)
            fondo = QColor(color)
            fondo.setAlpha(45)
            p.setPen(Qt.NoPen)
            p.setBrush(fondo)
            p.drawRoundedRect(caja, 11, 11)
            p.setPen(color)
            p.drawText(caja, int(Qt.AlignCenter), estado)
        p.restore()


class HistorialInterface(QWidget):
    pedir_nuevo = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("historial")
        self.cfg = cfg
        self.clientes = []
        self.actual = None
        self.trabajo = None

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        izq = self.izq = QWidget()
        v = self.v_izq = QVBoxLayout(izq)
        v.setContentsMargins(36, 28, 24, 24)
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
        self.b_nuevo.clicked.connect(lambda: self.pedir_nuevo.emit())
        cab.addWidget(self.b_nuevo, 0, Qt.AlignVCenter)
        v.addLayout(cab)

        self.k_cobrar = Kpi("Por cobrar", "#ff5a5f")
        self.k_mes = Kpi("Eventos del mes")
        self.k_comp = Kpi("Comprobantes")
        v.addWidget(Rejilla([self.k_cobrar, self.k_mes, self.k_comp], max_columnas=3, ancho_min=110))

        self.buscar = SearchLineEdit()
        self.buscar.setPlaceholderText("Buscar por nombre, teléfono, paquete o lugar…")
        self.buscar.textChanged.connect(self.refrescar)
        self.filtro = "Todos"
        self.seg = SegmentedWidget()
        for nombre in ("Todos", "Reservado", "Abonado", "Pagado"):
            self.seg.addItem(nombre, nombre, onClick=lambda n=nombre: self._filtrar(n))
        self.seg.setCurrentItem("Todos")
        self.seg.setMinimumWidth(300)
        self.seg.setMaximumWidth(380)
        self.fila_b = QBoxLayout(QBoxLayout.LeftToRight)       # en ventanas angostas, el filtro baja
        self.fila_b.setSpacing(12)
        self.fila_b.addWidget(self.buscar, 1)
        self.fila_b.addWidget(self.seg)
        v.addLayout(self.fila_b)

        self.tabla = TableWidget()
        self.tabla.setBorderVisible(True)
        self.tabla.setBorderRadius(8)
        self.tabla.setWordWrap(False)
        self.tabla.setColumnCount(len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setItemDelegate(DelegadoClientes(self.tabla))
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(56)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, ancho in ANCHOS.items():
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            self.tabla.setColumnWidth(col, ancho)
        h.setMinimumSectionSize(60)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        v.addWidget(self.tabla, 1)
        self.vacio = QWidget()
        ve = QVBoxLayout(self.vacio)
        ve.setSpacing(10)
        ve.addStretch(1)
        icono = IconWidget(FIF.PEOPLE)
        icono.setFixedSize(56, 56)
        ve.addWidget(icono, 0, Qt.AlignHCenter)
        ve.addWidget(SubtitleLabel("Aquí aparecerán tus clientes"), 0, Qt.AlignHCenter)
        ve.addWidget(CaptionLabel("Cada comprobante que generes queda guardado con su saldo y sus abonos."),
                     0, Qt.AlignHCenter)
        b_primero = PrimaryPushButton(FIF.ADD, "Crear el primer comprobante")
        b_primero.clicked.connect(lambda: self.pedir_nuevo.emit())
        ve.addWidget(b_primero, 0, Qt.AlignHCenter)
        ve.addStretch(2)
        v.addWidget(self.vacio, 1)
        raiz.addWidget(izq, 1)

        # ---------- Panel de detalle ----------
        self.panel = SimpleCardWidget()
        self.panel.setFixedWidth(360)
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
        p.setContentsMargins(20, 24, 20, 20)
        p.setSpacing(8)
        cabd = QHBoxLayout()
        cabd.setSpacing(12)
        self.d_avatar = Avatar("?", 46)
        cabd.addWidget(self.d_avatar, 0, Qt.AlignTop)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        self.d_nombre = SubtitleLabel("Selecciona un cliente")
        self.d_nombre.setWordWrap(True)
        self.d_info = CaptionLabel("")
        self.d_info.setWordWrap(True)
        tv.addWidget(self.d_nombre)
        tv.addWidget(self.d_info)
        cabd.addLayout(tv, 1)
        p.addLayout(cabd)
        self.d_barra = ProgressBar()
        self.d_barra.setRange(0, 100)
        p.addWidget(self.d_barra)
        fila, self.d_total = etiqueta_valor("Total del paquete")
        p.addWidget(fila)
        fila, self.d_pagado = etiqueta_valor("Pagado")
        p.addWidget(fila)
        fila, self.d_saldo = etiqueta_valor("Saldo pendiente")
        self.d_saldo.setTextColor(QColor("#e0262b"), QColor("#ff5a5f"))
        p.addWidget(fila)
        p.addWidget(HorizontalSeparator())
        p.addWidget(StrongBodyLabel("Pagos"))
        self.lista = ListWidget()
        self.lista.setFixedHeight(120)
        self.lista.itemDoubleClicked.connect(lambda it: abrir(it.data(Qt.UserRole)))
        p.addWidget(self.lista)
        self.b_ver = PushButton(FIF.VIEW, "Abrir")
        self.b_ver.clicked.connect(self._abrir_pago)
        self.b_copiar = PushButton(FIF.COPY, "Copiar")
        self.b_copiar.clicked.connect(self._copiar_pago)
        self.b_wa = PushButton(FIF.SEND, "WhatsApp")
        self.b_wa.clicked.connect(self._whatsapp)
        p.addWidget(Rejilla([self.b_ver, self.b_copiar, self.b_wa], max_columnas=3, ancho_min=100, espacio=8))
        p.addWidget(HorizontalSeparator())

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
        self.zona = ZonaCaptura(110)
        a.addWidget(self.zona)
        fila_z = QHBoxLayout()
        b_pegar = PushButton(FIF.PASTE, "Pegar captura")
        b_pegar.clicked.connect(self.zona.pegar)
        self.ring = IndeterminateProgressRing()
        self.ring.setFixedSize(22, 22)
        self.ring.hide()
        fila_z.addWidget(b_pegar)
        fila_z.addStretch(1)
        fila_z.addWidget(self.ring)
        a.addLayout(fila_z)
        self.b_abono = PrimaryPushButton(FIF.ACCEPT, "Generar comprobante de abono")
        self.b_abono.setFixedHeight(38)
        self.b_abono.clicked.connect(self.generar_abono)
        a.addWidget(self.b_abono)
        p.addWidget(self.caja_abono)
        self.pagado_ok = BodyLabel("✔ Este cliente ya pagó todo.")
        p.addWidget(self.pagado_ok)
        p.addStretch(1)
        self.b_borrar = TransparentPushButton(FIF.DELETE, "Eliminar cliente")
        self.b_borrar.clicked.connect(self.eliminar)
        p.addWidget(self.b_borrar)
        raiz.addWidget(self.panel)

        self._detalle(None)
        self.refrescar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ancho = self.width()
        # el panel de detalle se angosta en ventanas chicas (laptops, MacBook)
        self.panel.setFixedWidth(360 if ancho >= 1100 else (320 if ancho >= 900 else 290))
        chico = ancho < 900
        self.v_izq.setContentsMargins(*((20, 18, 16, 16) if chico else (36, 28, 24, 24)))
        self.p_panel.setContentsMargins(*((14, 18, 14, 14) if chico else (20, 24, 20, 20)))
        self.b_nuevo.setText("Nuevo" if ancho - self.panel.width() < 600 else "Nuevo comprobante")
        self.fila_b.setDirection(QBoxLayout.TopToBottom if ancho - self.panel.width() < 640 else QBoxLayout.LeftToRight)
        QTimer.singleShot(0, self._columnas)

    def _columnas(self):
        # Si la tabla queda angosta se ocultan columnas (el detalle las sigue mostrando),
        # para que el nombre del cliente, el saldo y el estado siempre se lean.
        ancho = self.tabla.viewport().width()
        self.tabla.setColumnHidden(COL_PAGADO, ancho < 780)
        self.tabla.setColumnHidden(COL_PAQUETE, ancho < 600)
        self.tabla.setColumnHidden(COL_FECHA, ancho < 470)

    # ---------- datos ----------
    def showEvent(self, e):
        super().showEvent(e)
        self.refrescar()

    def refrescar(self):
        r = registro.resumen()
        self.k_cobrar.poner(q(r["por_cobrar"]))
        self.k_mes.poner(str(r["eventos_mes"]))
        self.k_comp.poner(str(r["comprobantes"]))
        seleccion = self.actual.id if self.actual else None
        self.clientes = [c for c in registro.clientes(self.buscar.text())
                         if self.filtro == "Todos" or c.estado == self.filtro]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self.clientes))
        fila_sel = -1
        for f, c in enumerate(self.clientes):
            textos = {1: c.fecha_evento.strftime("%d/%m/%Y"),
                      2: f"{NOMBRES_PAQUETE.get(c.paquete, c.paquete)} · {c.evento}", 4: q(c.saldo)}
            for col in range(len(COLUMNAS)):
                it = QTableWidgetItem(textos.get(col, ""))
                if col == 1:
                    it.setToolTip(faltan(c.fecha_evento))
                if col == 4:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if c.saldo > 0:
                        it.setForeground(QColor("#ff5a5f"))
                self.tabla.setItem(f, col, it)
            self.tabla.item(f, 0).setData(DATOS, c.festejado)
            self.tabla.item(f, 0).setToolTip(f"{c.festejado} · {c.telefono}")
            self.tabla.item(f, COL_PAGADO).setData(DATOS, (c.pagado, c.total))
            self.tabla.item(f, COL_ESTADO).setData(DATOS, c.estado)
            self.tabla.setRowHeight(f, 56)
            if c.id == seleccion:
                fila_sel = f
        self.tabla.blockSignals(False)
        vacio = not self.clientes and not self.buscar.text() and self.filtro == "Todos"
        self.vacio.setVisible(vacio)
        self.tabla.setVisible(not vacio)
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
        self.d_avatar.setVisible(hay)
        self.d_barra.setVisible(hay)
        if not hay:
            self.d_nombre.setText("Selecciona un cliente")
            self.d_info.setText("Elige una fila de la tabla para ver sus pagos y registrar abonos.")
            for lab in (self.d_total, self.d_pagado, self.d_saldo):
                lab.setText("—")
            self.lista.clear()
            self.caja_abono.setVisible(False)
            self.t_abono.setVisible(False)
            self.pagado_ok.setVisible(False)
            return
        self.d_nombre.setText(c.festejado)
        self.d_avatar.poner(c.festejado)
        self.d_barra.setValue(int(100 * c.pagado / c.total) if c.total else 0)
        verde = c.saldo <= 0
        self.d_barra.setCustomBarColor(QColor("#2e9e57" if verde else "#e0262b"),
                                       QColor("#52be80" if verde else "#ff5a5f"))
        self.d_info.setText(f"{c.evento} · {NOMBRES_PAQUETE.get(c.paquete, c.paquete)} · "
                            f"{c.fecha_evento.strftime('%d/%m/%Y')} ({faltan(c.fecha_evento)})\n"
                            f"{c.lugar} · {c.telefono}")
        self.d_total.setText(q(c.total))
        self.d_pagado.setText(q(c.pagado))
        self.d_saldo.setText(q(c.saldo))
        self.lista.clear()
        for _, fecha, monto, concepto, comprobante in registro.pagos(c.id):
            it = QListWidgetItem(f"{date.fromisoformat(fecha).strftime('%d/%m/%Y')} · {concepto} · {q(monto)}")
            it.setData(Qt.UserRole, comprobante)
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
        self.b_abono.setText("Generar comprobante de abono")
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
