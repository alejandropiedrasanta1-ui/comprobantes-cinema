"""Pantalla «Paquetes»: lo que incluye cada paquete y su precio, editables con un clic (✕ quita un servicio,
«Agregar servicio» suma uno: de otro paquete, un extra con su opción o uno nuevo), y el catálogo de extras.
El comprobante dibuja la lista de servicios al generarse, así los cambios se ven en el próximo comprobante."""
import json

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (Action, BodyLabel, CaptionLabel, ComboBox, FluentIcon as FIF, LineEdit,
                            MessageBoxBase, PrimaryPushButton, PushButton, RoundMenu, SmoothScrollArea,
                            StrongBodyLabel, SubtitleLabel, TitleLabel, ToolTipFilter, TransparentPushButton,
                            TransparentToolButton)

import estilo
import motor
import rutas
from estilo import Icono, Pildora, Separador, Tarjeta
from lista import MAX_SERVICIOS
from ui_comun import COLOR_PAQUETE, ICONO_PAQUETE, NOMBRES_PAQUETE, Monto, Rejilla, aviso, q, servicio_legible

# Ícono de la lista del comprobante → nombre para elegirlo en «Otro servicio…»
NOMBRES_ICONO = {
    "camara": "Cámara y video", "cobertura": "Maquillaje", "album": "Álbum", "enmarcada": "Foto enmarcada",
    "video": "Video", "video_largo": "Claqueta", "dron": "Dron", "video_fotos": "Video con fotos",
    "buzon": "Teléfono", "galeria": "Enlace", "usb": "Memoria USB", "cabina360": "Cabina 360",
    "chispa": "Chispa", "cabina_fotos": "Cabina de fotos", "zancos": "Zancos", "telefono": "Teléfono antiguo",
    "espejo": "Espejo", "backdrop": "Fondo para fotos", "cabezones": "Cabezón",
}


def _iconos_disponibles():
    """Íconos que tiene la plantilla (los que el comprobante puede dibujar)."""
    try:
        archivo = rutas.recurso("PLANTILLAS/COMPROBANTE.json")
        return [k for k in json.loads(open(archivo, encoding="utf-8").read())["iconos"] if k in NOMBRES_ICONO]
    except (OSError, ValueError, KeyError):
        return list(NOMBRES_ICONO)


class _FilaServicio(QWidget):
    """«✓ [ícono] Título · detalle  ✕»: el ✕ lo quita del paquete con un clic."""
    quitar = Signal()

    def __init__(self, titulo, detalle, icono_s, parent=None):
        super().__init__(parent)
        titulo, detalle = servicio_legible(titulo, detalle)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(10)
        check = QLabel("✓")
        check.setStyleSheet(f"color:{estilo.VERDE};font-weight:700;font-size:13px;background:transparent;")
        check.setFixedWidth(12)
        h.addWidget(check, 0, Qt.AlignTop)
        h.addWidget(Icono(icono_s, 16), 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(0)
        t = StrongBodyLabel(titulo)
        f = t.font()
        f.setPixelSize(13)
        t.setFont(f)
        t.setWordWrap(True)
        v.addWidget(t)
        if detalle:
            d = CaptionLabel(detalle)
            d.setWordWrap(True)
            v.addWidget(d)
        h.addLayout(v, 1)
        x = TransparentToolButton(FIF.CLOSE)
        x.setFixedSize(24, 24)
        x.setIconSize(QSize(9, 9))
        x.setToolTip("Quitar del paquete")
        x.installEventFilter(ToolTipFilter(x))
        x.clicked.connect(self.quitar)
        h.addWidget(x, 0, Qt.AlignTop)


class _OtroServicio(MessageBoxBase):
    """Un servicio nuevo: título, detalle y su ícono."""

    def __init__(self, parent):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel("Otro servicio"))
        self.titulo = LineEdit()
        self.titulo.setPlaceholderText("Título (p. ej. Sesión de fotos previa)")
        self.detalle = LineEdit()
        self.detalle.setPlaceholderText("Detalle, opcional (p. ej. 1 hora en exteriores)")
        self.icono = ComboBox()
        for k in _iconos_disponibles():
            self.icono.addItem(NOMBRES_ICONO[k], estilo.icono(k), userData=k)
        for etiqueta, w in (("Título", self.titulo), ("Detalle", self.detalle), ("Ícono", self.icono)):
            self.viewLayout.addWidget(CaptionLabel(etiqueta))
            self.viewLayout.addWidget(w)
        self.yesButton.setText("Agregar")
        self.cancelButton.setText("Cancelar")
        self.widget.setMinimumWidth(380)
        self.titulo.setFocus()

    def validate(self):
        return bool(self.titulo.text().strip())

    def item(self):
        detalle = self.detalle.text().strip()
        if detalle and not detalle.startswith("("):
            detalle = f"({detalle})"
        return [self.titulo.text().strip(), detalle, self.icono.currentData() or "camara"]


class PaquetesInterface(QWidget):
    precios_cambiados = Signal()      # precios o servicios guardados: «Nuevo comprobante» se actualiza

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("paquetes")
        self.cfg = cfg
        self.defecto = motor.config_por_defecto()["paquetes"]
        # copia editable de cada paquete (se guarda con «Guardar cambios»)
        self.editado = {k: {"precio": int(p["precio"]), "incluye": [list(i) for i in p.get("incluye", [])]}
                        for k, p in cfg["paquetes"].items()}
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        # la cabecera queda fija arriba: «Guardar cambios» siempre a la vista aunque se desplace la lista
        cabecera = QWidget()
        cab = QHBoxLayout(cabecera)
        cab.setContentsMargins(32, 24, 32, 14)
        raiz.addWidget(cabecera)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent")
        scroll.setWidget(cont)
        raiz.addWidget(scroll, 1)
        v = self.v = QVBoxLayout(cont)
        v.setContentsMargins(32, 4, 32, 28)
        v.setSpacing(18)

        tit = QVBoxLayout()
        tit.setSpacing(2)
        tit.addWidget(TitleLabel("Paquetes"))
        sub = CaptionLabel("Precios y servicios de cada paquete: ✕ quita un servicio, «Agregar servicio» suma uno.")
        sub.setWordWrap(True)
        tit.addWidget(sub)
        cab.addLayout(tit, 1)
        self.nota_cambios = CaptionLabel("")
        cab.addWidget(self.nota_cambios, 0, Qt.AlignVCenter)
        cab.addSpacing(8)
        self.b_guardar = PrimaryPushButton(FIF.SAVE, "Guardar cambios")
        self.b_guardar.setFixedHeight(38)
        estilo.boton_principal(self.b_guardar, FIF.SAVE)
        self.b_guardar.clicked.connect(self.guardar)
        cab.addWidget(self.b_guardar, 0, Qt.AlignVCenter)

        self.precios, self.listas, self.titulos_lista, self.restablecer, self.agregar = {}, {}, {}, {}, {}
        self.filas = {}
        tarjetas = [self._tarjeta(clave) for clave in cfg["paquetes"]]
        self.rejilla = Rejilla(tarjetas, max_columnas=4, ancho_min=236, espacio=16, validas=(1, 2, 4),
                               misma_altura=True)
        v.addWidget(self.rejilla)

        # Catálogo de extras
        fila = QHBoxLayout()
        fila.setSpacing(10)
        fila.addWidget(Icono("chispa", 20))
        fila.addWidget(SubtitleLabel("Extras"))
        fila.addStretch(1)
        v.addLayout(fila)
        expl = CaptionLabel("Se suman a cualquier paquete: fijos desde «Agregar servicio» de arriba, o solo para un "
                            "cliente con «Agregar extra» en Nuevo comprobante (su precio se suma al total).")
        expl.setWordWrap(True)
        v.addWidget(expl)
        v.addWidget(Rejilla([self._tarjeta_extra(e) for e in cfg.get("extras", [])], max_columnas=4,
                            ancho_min=200, espacio=12, validas=(1, 2, 4), misma_altura=True))

        nota = Tarjeta(nivel=2, radio=12)
        hn = QHBoxLayout(nota)
        hn.setContentsMargins(16, 12, 16, 12)
        hn.setSpacing(12)
        hn.addWidget(Icono("ajustes", 18))
        texto = CaptionLabel(f"Los cambios se usan desde el próximo comprobante. Cada comprobante admite hasta "
                             f"{MAX_SERVICIOS} servicios; con muchos, la letra de la lista se achica para que quepan.")
        texto.setWordWrap(True)
        hn.addWidget(texto, 1)
        v.addWidget(nota)
        v.addStretch(1)
        for clave in cfg["paquetes"]:
            self._poner_servicios(clave)
        self._contar_cambios()

    # ---- Tarjetas ----
    def _tarjeta(self, clave):
        color = COLOR_PAQUETE.get(clave, "#888888")
        destacado = self.cfg.get("paquete_destacado", "COMPLETO")
        reserva = self.cfg.get("reserva_por_defecto", 600)
        card = Tarjeta(acento=color)
        card.resaltada = clave == destacado
        card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # las 4 columnas, del mismo ancho
        c = QVBoxLayout(card)
        c.setContentsMargins(20, 22, 20, 18)
        c.setSpacing(10)
        fila = QHBoxLayout()
        fila.setSpacing(12)
        fila.addWidget(Icono(ICONO_PAQUETE.get(clave, "camara"), 22, color=color, fondo=color, caja=42))
        fila.addWidget(SubtitleLabel(NOMBRES_PAQUETE.get(clave, clave.title())), 1)
        c.addLayout(fila)
        precio = Monto()
        precio.setValue(self.editado[clave]["precio"])
        precio.setMinimumWidth(150)
        precio.valueChanged.connect(lambda v, k=clave: self._precio(k, v))
        self.precios[clave] = precio
        c.addWidget(precio)
        fila_r = QHBoxLayout()
        fila_r.setSpacing(6)
        fila_r.addWidget(Icono("recibo", 14))
        fila_r.addWidget(CaptionLabel(f"Reserva sugerida {q(reserva)}"))
        fila_r.addStretch(1)
        if clave == destacado:          # aquí sobra lugar: así el nombre del paquete nunca se corta
            fila_r.addWidget(Pildora("Más vendido", estilo.ROJO, solida=True, tam_letra=10, alto=22), 0,
                             Qt.AlignVCenter)
        c.addLayout(fila_r)
        c.addWidget(Separador())
        cab = QHBoxLayout()
        cab.setSpacing(4)
        self.titulos_lista[clave] = StrongBodyLabel("")
        cab.addWidget(self.titulos_lista[clave], 1)
        r = TransparentPushButton(FIF.SYNC, "Restablecer")
        r.setToolTip("Volver a los servicios y al precio originales de este paquete")
        r.installEventFilter(ToolTipFilter(r))
        r.clicked.connect(lambda _=False, k=clave: self._restablecer(k))
        self.restablecer[clave] = r
        cab.addWidget(r)
        c.addLayout(cab)
        caja = QWidget()
        self.listas[clave] = QVBoxLayout(caja)
        self.listas[clave].setContentsMargins(0, 0, 0, 0)
        self.listas[clave].setSpacing(2)
        c.addWidget(caja)
        c.addStretch(1)
        b = PushButton(FIF.ADD, "Agregar servicio")
        b.clicked.connect(lambda _=False, k=clave, w=b: self._menu_agregar(k, w))
        self.agregar[clave] = b
        c.addWidget(b)
        return card

    def _tarjeta_extra(self, extra):
        card = Tarjeta(nivel=2, radio=12)
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 14, 16, 14)
        c.setSpacing(6)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        fila.addWidget(Icono(extra["icono"], 18, caja=34))
        t = StrongBodyLabel(extra["titulo"])
        t.setWordWrap(True)
        fila.addWidget(t, 1)
        c.addLayout(fila)
        for texto, precio in extra["opciones"]:
            f = QHBoxLayout()
            f.addWidget(CaptionLabel(texto), 1)
            p = BodyLabel(q(precio))
            p.setFont(estilo.fuente_numeros(13))
            f.addWidget(p)
            c.addLayout(f)
        c.addStretch(1)
        return card

    def _poner_servicios(self, clave):
        lay = self.listas[clave]
        while lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        incluye = self.editado[clave]["incluye"]
        for i, (titulo, detalle, icono) in enumerate(incluye):
            fila = _FilaServicio(titulo, detalle, icono)
            fila.quitar.connect(lambda k=clave, i=i: self._quitar(k, i))
            lay.addWidget(fila)
        self.titulos_lista[clave].setText(f"Incluye ({len(incluye)} servicio{'s' if len(incluye) != 1 else ''})")
        b = self.agregar[clave]
        lleno = len(incluye) >= MAX_SERVICIOS
        b.setEnabled(not lleno)
        b.setToolTip(f"Máximo {MAX_SERVICIOS} servicios por comprobante" if lleno else "")
        d = self.defecto.get(clave, {})
        self.restablecer[clave].setVisible(incluye != d.get("incluye") or self.editado[clave]["precio"] != d.get("precio"))
        self.rejilla.updateGeometry()
        self._contar_cambios()

    # ---- Agregar y quitar ----
    def _catalogo(self, clave):
        """Servicios de los otros paquetes (y de los originales) que este paquete todavía no tiene."""
        tiene = {tuple(i[:2]) for i in self.editado[clave]["incluye"]}
        vistos, lista = set(tiene), []
        fuentes = [p.get("incluye", []) for p in self.defecto.values()] + \
                  [p["incluye"] for p in self.editado.values()]
        extras = {(e["titulo"], motor.item_extra(e, i)[1]) for e in self.cfg.get("extras", [])
                  for i in range(len(e["opciones"]))}
        for incluye in fuentes:
            for item in incluye:
                k = tuple(item[:2])
                if k not in vistos and k not in extras:
                    vistos.add(k)
                    lista.append(list(item))
        return lista

    def _menu_agregar(self, clave, boton):
        menu = RoundMenu(parent=self)
        for item in self._catalogo(clave):
            titulo, detalle = servicio_legible(item[0], item[1])
            a = Action(estilo.icono(item[2]), f"{titulo}" + (f"  ·  {detalle}" if detalle else ""), self)
            a.triggered.connect(lambda _=False, k=clave, it=item: self._agregar(k, it))
            menu.addAction(a)
        if self.cfg.get("extras"):
            menu.addSeparator()
            for extra in self.cfg["extras"]:
                sub = RoundMenu(extra["titulo"], self)
                sub.setIcon(estilo.icono(extra["icono"]))
                for i, (texto, precio) in enumerate(extra["opciones"]):
                    a = Action(f"{texto}  ·  +{q(precio)}", self)
                    a.triggered.connect(lambda _=False, k=clave, e=extra, o=i: self._agregar(
                        k, motor.item_extra(e, o), motor.precio_extra(e, o)))
                    sub.addAction(a)
                menu.addMenu(sub)
        menu.addSeparator()
        otro = Action(FIF.EDIT, "Otro servicio…", self)
        otro.triggered.connect(lambda _=False, k=clave: self._otro(k))
        menu.addAction(otro)
        menu.exec(boton.mapToGlobal(QPoint(0, boton.height() + 4)))

    def _otro(self, clave):
        dlg = _OtroServicio(self.window())
        if dlg.exec():
            self._agregar(clave, dlg.item())

    def _agregar(self, clave, item, precio=0):
        incluye = self.editado[clave]["incluye"]
        if len(incluye) >= MAX_SERVICIOS:
            return
        incluye[:] = motor.con_extras(incluye, [item])    # antes de «Memoria USB y link» (la entrega va al final)
        if precio:
            self.precios[clave].setValue(int(self.precios[clave].value() + precio))
            aviso(self, "info", "Precio actualizado",
                  f"{NOMBRES_PAQUETE.get(clave, clave)}: +{q(precio)} por {item[0]} {item[1]}.")
        self._poner_servicios(clave)

    def _quitar(self, clave, i):
        incluye = self.editado[clave]["incluye"]
        if not 0 <= i < len(incluye):
            return
        item = incluye.pop(i)
        precio = motor.precio_item(self.cfg, item)      # si era un extra, su precio se descuenta
        if precio:
            self.precios[clave].setValue(int(max(self.precios[clave].value() - precio, 0)))
        self._poner_servicios(clave)

    def _restablecer(self, clave):
        d = self.defecto.get(clave, {})
        self.editado[clave]["incluye"] = [list(i) for i in d.get("incluye", [])]
        self.precios[clave].setValue(int(d.get("precio", self.precios[clave].value())))
        self._poner_servicios(clave)

    def _precio(self, clave, valor):
        self.editado[clave]["precio"] = int(valor)
        self._contar_cambios()
        d = self.defecto.get(clave, {})
        self.restablecer[clave].setVisible(self.editado[clave]["incluye"] != d.get("incluye")
                                           or int(valor) != d.get("precio"))

    # ---- Guardar ----
    def _contar_cambios(self, *_):
        if not hasattr(self, "b_guardar"):
            return
        n = sum(self.editado[k]["precio"] != int(p["precio"]) or self.editado[k]["incluye"] != p.get("incluye", [])
                for k, p in self.cfg["paquetes"].items())
        self.nota_cambios.setText(f"{n} paquete{'s' if n != 1 else ''} con cambios sin guardar" if n else "")
        self.b_guardar.setEnabled(bool(n))

    def guardar(self):
        nuevos = {}
        for clave, e in self.editado.items():
            nuevos[clave] = {"precio": e["precio"]}
            if e["incluye"] != self.defecto.get(clave, {}).get("incluye"):   # solo si cambió: así una lista
                nuevos[clave]["incluye"] = e["incluye"]                     # nueva del programa sí llega
            self.cfg["paquetes"][clave]["precio"] = e["precio"]
            self.cfg["paquetes"][clave]["incluye"] = [list(i) for i in e["incluye"]]
        motor.guardar_preferencia("paquetes", nuevos)
        self._contar_cambios()
        self.precios_cambiados.emit()
        aviso(self, "success", "Paquetes guardados", "Los próximos comprobantes usarán estos precios y servicios.")
