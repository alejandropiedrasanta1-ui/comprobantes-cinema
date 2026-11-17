"""Pantalla «Nuevo comprobante» — vista previa protagonista.

Izquierda: 3 bloques plegables (cliente y evento · paquete · pago y captura) que se marcan con ✓.
Derecha: vista previa grande que se actualiza sola mientras escribes.
Abajo: barra fija con el saldo y los botones Copiar / WhatsApp / Generar."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (CalendarPicker, CaptionLabel, FlowLayout, FluentIcon as FIF,
                            IndeterminateProgressRing, LineEdit, PrimaryPushButton, PushButton,
                            SegmentedWidget, SmoothScrollArea, StrongBodyLabel, SwitchButton,
                            TitleLabel, ToolTipFilter, TransparentPushButton, TransparentToolButton,
                            isDarkTheme)

import motor
import registro
import rutas
from ui_comun import (CTRL, NOMBRES_PAQUETE, Bloque, Monto, Rejilla, TarjetaPaquete, Trabajo, ZonaCaptura, abrir,
                      abrir_whatsapp, aviso, copiar_imagen, digitos_telefono, faltan, fecha_larga,
                      formatear_telefono, q)

ANCHO_COMPACTO = 900     # por debajo: se ve el formulario o la vista previa (botón para cambiar), no los dos
ANCHO_BARRA_CORTA = 780  # por debajo: la barra inferior se simplifica


def _campo(titulo, widget, nota=None):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    v.addWidget(CaptionLabel(titulo))
    v.addWidget(widget)
    if nota is not None:
        v.addWidget(nota)
    return w


def _chip(texto):
    lab = QLabel(texto)
    oscuro = isDarkTheme()
    lab.setStyleSheet(f"background:{'#26262b' if oscuro else '#ececf0'};"
                      f"border:1px solid {'#33333a' if oscuro else '#dcdce2'};border-radius:10px;"
                      f"padding:2px 9px;font-size:12px;color:{'#d8d8dc' if oscuro else '#333'};")
    return lab


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

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(0)
        raiz.addLayout(cuerpo, 1)

        # ================= Formulario en bloques =================
        scroll = self.scroll_form = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        v = self.v_form = QVBoxLayout(cont)
        v.setContentsMargins(32, 24, 20, 20)
        v.setSpacing(12)

        cab = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(2)
        tit.addWidget(TitleLabel("Nuevo comprobante"))
        self.progreso = CaptionLabel("")
        self.progreso.setWordWrap(True)
        tit.addWidget(self.progreso)
        cab.addLayout(tit, 1)
        b_limpiar = TransparentPushButton(FIF.BROOM, "Limpiar")
        b_limpiar.setToolTip(f"Empezar un comprobante nuevo ({CTRL}N)")
        b_limpiar.installEventFilter(ToolTipFilter(b_limpiar))
        b_limpiar.clicked.connect(self.limpiar)
        cab.addWidget(b_limpiar, 0, Qt.AlignVCenter)
        self.b_ver_vista = PushButton(FIF.VIEW, "Vista previa")      # solo en ventanas angostas
        self.b_ver_vista.clicked.connect(lambda: self._ver_vista(True))
        cab.addWidget(self.b_ver_vista, 0, Qt.AlignVCenter)
        v.addLayout(cab)

        # ---- ① Cliente y evento ----
        self.b1 = Bloque(1, "Cliente y evento")
        self.seg = SegmentedWidget()
        for nombre in cfg["eventos"]:
            self.seg.addItem(nombre, nombre, onClick=lambda n=nombre: self._evento(n))
        self.seg.setCurrentItem(self.evento)
        self.seg.setFixedWidth(230)
        self.b1.cuerpo.addWidget(self.seg)
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
            _campo("Teléfono del cliente (WhatsApp)", self.telefono)], max_columnas=2, ancho_min=230))
        sig1 = PushButton(FIF.CHEVRON_RIGHT_MED, "Siguiente: paquete")
        sig1.clicked.connect(lambda: self.abrir_bloque(self.b2))
        self.b1.cuerpo.addWidget(sig1, 0, Qt.AlignRight)
        v.addWidget(self.b1)

        # ---- ② Paquete ----
        self.b2 = Bloque(2, "Paquete")
        self.tarjetas = {}
        destacado = cfg.get("paquete_destacado", "COMPLETO")
        for clave, paq in cfg["paquetes"].items():
            t = TarjetaPaquete(clave, paq, destacado=(clave == destacado))
            t.elegida.connect(self.elegir_paquete)
            self.tarjetas[clave] = t
        self.b2.cuerpo.addWidget(Rejilla(list(self.tarjetas.values()), max_columnas=2, ancho_min=190, espacio=8))
        self.b2.cuerpo.addWidget(CaptionLabel("Incluye"))
        self.chips = QWidget()
        self.flow = FlowLayout(self.chips, needAni=False)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setHorizontalSpacing(6)
        self.flow.setVerticalSpacing(6)
        self.b2.cuerpo.addWidget(self.chips)
        sig2 = PushButton(FIF.CHEVRON_RIGHT_MED, "Siguiente: pago")
        sig2.clicked.connect(lambda: self.abrir_bloque(self.b3))
        self.b2.cuerpo.addWidget(sig2, 0, Qt.AlignRight)
        v.addWidget(self.b2)

        # ---- ③ Pago y captura ----
        self.b3 = Bloque(3, "Pago y captura")
        self.total = Monto()
        self.reserva = Monto()
        self.fecha_pago = CalendarPicker()
        self.fecha_pago.setDateFormat("dd/MM/yyyy")
        self.fecha_pago.setDate(QDate.currentDate())
        self.b3.cuerpo.addWidget(Rejilla([
            _campo("Precio del paquete", self.total), _campo("Reserva / anticipo", self.reserva),
            _campo("Fecha del pago", self.fecha_pago)], max_columnas=3, ancho_min=150))
        self.zona = ZonaCaptura(120)
        self.b3.cuerpo.addWidget(self.zona)
        fila = QHBoxLayout()
        b_subir = PushButton(FIF.PHOTO, "Subir imagen")
        b_pegar = PushButton(FIF.PASTE, f"Pegar ({CTRL}V)")
        b_subir.clicked.connect(self.zona.buscar)
        b_pegar.clicked.connect(self.zona.pegar)
        fila.addWidget(b_subir)
        fila.addWidget(b_pegar)
        fila.addStretch(1)
        self.b3.cuerpo.addLayout(fila)
        v.addWidget(self.b3)
        v.addStretch(1)

        self.bloques = [self.b1, self.b2, self.b3]
        for b in self.bloques:
            b.pedir_abrir.connect(self.abrir_bloque)
        cuerpo.addWidget(scroll, 46)

        # ================= Vista previa protagonista =================
        panel = self.panel_vista = QFrame()
        panel.setObjectName("panelVista")
        panel.setStyleSheet("#panelVista{background: rgba(0,0,0,0.18); border-left: 1px solid rgba(128,128,128,0.18);}")
        p = QVBoxLayout(panel)
        p.setContentsMargins(20, 22, 20, 12)
        p.setSpacing(8)
        cabv = QHBoxLayout()
        self.b_volver = TransparentPushButton(FIF.LEFT_ARROW, "Datos")     # solo en ventanas angostas
        self.b_volver.clicked.connect(lambda: self._ver_vista(False))
        cabv.addWidget(self.b_volver)
        self.titulo_vista = StrongBodyLabel("Vista previa en vivo")
        self.ring = IndeterminateProgressRing()
        self.ring.setFixedSize(18, 18)
        self.ring.setStrokeWidth(3)
        self.ring.hide()
        cabv.addWidget(self.titulo_vista)
        cabv.addWidget(self.ring)
        cabv.addStretch(1)
        cabv.addWidget(CaptionLabel("En vivo"))
        self.en_vivo = SwitchButton()
        self.en_vivo.setOnText("")
        self.en_vivo.setOffText("")
        self.en_vivo.setChecked(bool(cfg.get("vista_en_vivo", True)))
        self.en_vivo.checkedChanged.connect(self._cambiar_en_vivo)
        cabv.addWidget(self.en_vivo)
        self.b_zoom = TransparentToolButton(FIF.ZOOM_IN)
        self.b_zoom.setToolTip("Ampliar / ajustar")
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
        self.area.setAlignment(Qt.AlignCenter)
        self.lienzo = QLabel()
        self.lienzo.setAlignment(Qt.AlignCenter)
        self.lienzo.setStyleSheet("background:transparent")
        self.area.setWidget(self.lienzo)
        self.area.setWidgetResizable(False)
        p.addWidget(self.area, 1)
        cuerpo.addWidget(panel, 54)

        # ================= Barra fija inferior =================
        barra = QFrame()
        barra.setObjectName("barraAcciones")
        barra.setFixedHeight(78)
        barra.setStyleSheet("#barraAcciones{background: rgba(128,128,128,0.08);"
                            "border-top: 1px solid rgba(128,128,128,0.22);}")
        hb = self.hb_barra = QHBoxLayout(barra)
        hb.setContentsMargins(32, 8, 20, 8)
        hb.setSpacing(10)
        sv = QVBoxLayout()
        sv.setSpacing(0)
        sv.addWidget(CaptionLabel("Saldo pendiente"))
        self.saldo = TitleLabel("Q0")
        self.saldo.setTextColor(QColor("#e0262b"), QColor("#ff5a5f"))
        sv.addWidget(self.saldo)
        hb.addLayout(sv)
        hb.addSpacing(16)
        self.resumen = CaptionLabel("")
        self.resumen.setWordWrap(True)
        self.resumen.setMinimumWidth(0)
        hb.addWidget(self.resumen, 1)
        self.btn_copiar = PushButton(FIF.COPY, "Copiar")
        self.btn_copiar.clicked.connect(self.copiar)
        self.btn_wa = PushButton(FIF.SEND, "WhatsApp")
        self.btn_wa.setToolTip("Abre el chat del cliente; el comprobante queda copiado para pegar")
        self.btn_wa.installEventFilter(ToolTipFilter(self.btn_wa))
        self.btn_wa.clicked.connect(self.whatsapp)
        self.btn_generar = PrimaryPushButton(FIF.ACCEPT, "Generar comprobante")
        self.btn_generar.setToolTip(f"{CTRL}Enter")
        self.btn_generar.installEventFilter(ToolTipFilter(self.btn_generar))
        self.btn_generar.setFixedHeight(40)
        self.btn_generar.setMinimumWidth(210)
        self.btn_generar.clicked.connect(self.generar)
        hb.addWidget(self.btn_copiar)
        hb.addWidget(self.btn_wa)
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
        for b in self.bloques:
            b.abrir(b is bloque)
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
        self.flow.takeAllWidgets()
        for titulo, _, _ in paq.get("incluye", []):
            self.flow.addWidget(_chip(titulo))
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
        self.nota_fecha.setText(f"{fecha_larga(fe).capitalize()} · {faltan(fe)}")
        f1 = [n for n, ok in (("festejado", self.festejado.text().strip()),
                              ("lugar", self.lugar.text().strip()),
                              ("teléfono", len(digitos_telefono(self.telefono.text())) >= 10)) if not ok]
        self.b1.poner_estado(not f1, " · ".join(x for x in (
            self.festejado.text().strip() or "Sin nombre", self.lugar.text().strip(),
            fe.strftime("%d/%m/%Y"), self.telefono.text().strip(), self.evento) if x))
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
                                     f"captura {'✓' if self.zona.ruta else 'pendiente'}")
        faltantes = f1 + f3
        listos = sum(b.completo for b in self.bloques)
        self.progreso.setText(f"{listos} de 3 listos" + (f" · falta: {', '.join(faltantes)}" if faltantes else
                                                        " · todo listo para generar"))
        self.saldo.setText(q(max(self.total.value() - self.reserva.value(), 0)))
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
        prop = 3508 / 2480   # las plantillas son A4 vertical
        ancho = max(vp.width() - 8, 400) * (1.8 if self.zoom else 1)
        alto = ancho * prop if self.zoom else min(max(vp.height() - 8, 400), ancho * prop)
        return int(max(600, min(alto * self.devicePixelRatioF(), motor.SesionPhotoCraft.LADO_MAX)))

    def _ajustar_imagen(self):
        if not getattr(self, "pix", None) or self.pix.isNull() or not self.panel_vista.isVisible():
            return
        vp = self.area.viewport().size()
        dpr = self.devicePixelRatioF()          # pantallas Retina / 4K: la imagen se escala a sus píxeles reales
        if self.zoom:
            ancho = max(vp.width() - 8, 400) * 1.8
            img = self.pix.scaledToWidth(int(ancho * dpr), Qt.SmoothTransformation)
        else:
            img = self.pix.scaled(int((vp.width() - 8) * dpr), int((vp.height() - 8) * dpr),
                                  Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img.setDevicePixelRatio(dpr)
        self.lienzo.setPixmap(img)
        self.lienzo.resize(img.deviceIndependentSize().toSize())
        if (self.en_vivo.isChecked() and self.vista_ruta and self._imagen_actual() == self.vista_ruta
                and max(self.pix.width(), self.pix.height()) + 48 < self._lado_vista()):
            self.temporizador.start()   # la ventana creció o hay zoom: pedir la vista más nítida

    def _alternar_zoom(self):
        self.zoom = not self.zoom
        self.b_zoom.setIcon(FIF.ZOOM_OUT if self.zoom else FIF.ZOOM_IN)
        self._ajustar_imagen()

    # ================= Tamaño de la ventana =================
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
            self.v_form.setContentsMargins(*((20, 18, 16, 16) if compacto else (32, 24, 20, 20)))
        self.scroll_form.setVisible(not compacto or not self.viendo_vista)
        self.panel_vista.setVisible(not compacto or self.viendo_vista)
        corta = ancho < ANCHO_BARRA_CORTA
        self.resumen.setVisible(not corta)
        self.hb_barra.setContentsMargins(*((16, 8, 12, 8) if corta else (32, 8, 20, 8)))
        self.btn_generar.setText("Generar" if corta else "Generar comprobante")
        self.btn_generar.setMinimumWidth(130 if corta else 210)
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
        self.trabajo = Trabajo(self.datos, self.cfg)
        self.trabajo.listo.connect(self._listo)
        self.trabajo.fallo.connect(self._fallo)
        self.trabajo.start()

    def _fin(self):
        self.btn_generar.setEnabled(True)
        self.ring.hide()
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
        aviso(self, "success", "Comprobante corregido" if corregido else "Comprobante listo",
              f"Guardado y copiado: pégalo en WhatsApp con {CTRL}V.", 7000, ruta_abrir=ruta)

    def _fallo(self, msg):
        self._fin()
        self.estado.setText("No se pudo generar.")
        aviso(self, "error", "Error", msg, 10000)
