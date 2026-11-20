"""Dibuja el comprobante dentro del programa (sin PhotoCraft), igual en Windows y en Mac.

Parte del diseño exportado una vez del PSD (PLANTILLAS/DISENO, ver herramientas/exportar_diseno.py): el
fondo con todo lo fijo, los íconos y, para cada texto que cambia, su posición, letra, tamaño y escala tal
como los tiene la plantilla. Los textos se escriben con las letras incluidas en recursos/fuentes (no hace
falta instalarlas) y la lista de servicios se acomoda con las mismas reglas que lista.py.

Un comprobante completo (2480×3508) tarda ≈0,1 s; la vista en vivo se dibuja directo del tamaño de la
pantalla (≈20 ms)."""
import json
import threading
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter,
                           QPainterPath, QPen)

import lista
import rutas

PX_POR_PT = 4.1666667
REF_PX = 200                   # tamaño de referencia de la letra: se escala con el pintor (tamaños exactos)
INCLINACION = 0.21             # cursiva simulada del detalle de la lista (como «Faux Italic»)
RADIO_CAPTURA = 30             # esquinas del marco de la captura (forma de pantalla de celular)
ARCHIVOS_FUENTE = {            # nombre PostScript (como lo guarda el PSD) → archivo en recursos/fuentes
    "LEMONMILK-Bold": "LEMONMILK-Bold.otf",
    "MyriadPro-Bold": "MYRIADPRO-BOLD.OTF",
    "MyriadPro-Regular": "MYRIADPRO-REGULAR.OTF",
    "GetVoIPGrotesque": "GetVoIP Grotesque.otf",
}
FUENTE_TITULO_LISTA = "GetVoIPGrotesque"
FUENTE_DETALLE_LISTA = "LEMONMILK-Bold"

_candado = threading.Lock()
_familias = {}                 # nombre PostScript → (familia, estilo) para Qt
_diseno = None
_piezas = {}                   # nombre → QImage
_fondos = {}                   # ancho → fondo ya escalado (la vista en vivo pide siempre el mismo)
_app = None


def carpeta():
    return Path(rutas.recurso("PLANTILLAS/DISENO"))


def preparar():
    """Carga las letras y el diseño (una vez). Conviene llamarla al abrir el programa, en el hilo
    principal; si no hay aplicación de Qt (pruebas sin ventana) se crea una."""
    global _diseno, _app
    with _candado:
        if _diseno is not None:
            return _diseno
        if QGuiApplication.instance() is None:
            _app = QGuiApplication([])
        for ps, archivo in ARCHIVOS_FUENTE.items():
            ruta = rutas.recurso(f"recursos/fuentes/{archivo}")
            fid = QFontDatabase.addApplicationFont(str(ruta))
            if fid < 0:
                raise RuntimeError(f"No se pudo cargar la letra {archivo}")
            familia = QFontDatabase.applicationFontFamilies(fid)[0]
            _familias[ps] = (familia, QFont.Bold if "Bold" in ps else QFont.Normal)
        d = json.loads((carpeta() / "diseno.json").read_text(encoding="utf-8"))
        for nombre in d["piezas"]:
            img = QImage(str(carpeta() / f"{nombre}.png"))
            if img.isNull():
                raise RuntimeError(f"Falta la pieza del diseño: {nombre}.png")
            _piezas[nombre] = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        fondo = QImage(str(carpeta() / "fondo.jpg"))
        if fondo.isNull():
            raise RuntimeError("Falta el fondo del comprobante (PLANTILLAS/DISENO/fondo.jpg)")
        _fondos[fondo.width()] = fondo.convertToFormat(QImage.Format_RGB32)
        _diseno = d
        return d


def diseno():
    return _diseno or preparar()


# ================= Letras =================
def fuente(ps):
    """La letra a tamaño de referencia (REF_PX), sin ajuste a la rejilla de píxeles: así se escala
    exacta con el pintor a cualquier tamaño, también fraccionario."""
    familia, peso = _familias.get(ps) or _familias["MyriadPro-Bold"]
    f = QFont(familia)
    f.setWeight(peso)
    f.setPixelSize(REF_PX)
    f.setHintingPreference(QFont.PreferNoHinting)
    f.setKerning(True)
    return f


def ancho(ps, texto, px):
    """Ancho (px de la hoja) del texto con la letra ps de px de alto."""
    return QFontMetricsF(fuente(ps)).horizontalAdvance(texto) * px / REF_PX


def _escribir(p, ps, texto, x, y, px, escala_h=1.0, color="#000000", inclinar=0.0):
    """Escribe texto con la línea base en (x, y) (px de la hoja)."""
    p.save()
    p.translate(x, y)
    k = px / REF_PX
    p.scale(k * escala_h, k)
    if inclinar:
        p.shear(-inclinar, 0)
    p.setFont(fuente(ps))
    p.setPen(QColor(color))
    p.drawText(QPointF(0, 0), texto)
    p.restore()


# ================= Textos de la plantilla =================
class Texto:
    """Un texto de la plantilla: dónde empieza (o su centro), su letra y su tamaño."""

    def __init__(self, t):
        a, _, _, dd, tx, ty = t["transform"]
        self.ps, self.pt, self.color = t["fuente"], t["pt"], t["color"]
        self.sx, self.sy, self.x, self.y = a, dd, tx, ty
        self.escala_h = t.get("escala_h", 1.0) * a / dd
        self.centrado = t.get("alineacion") == "Center"
        self.caja = t["caja"]                     # x0, y0, x1, y1 en la plantilla

    def px(self, pt=None):
        return (pt or self.pt) * PX_POR_PT * self.sy

    def ancho(self, texto, pt=None):
        return max((ancho(self.ps, l, self.px(pt)) * self.escala_h for l in texto.split("\n")), default=0)

    def centro_original(self):
        return (self.caja[0] + self.caja[2]) / 2


def acomodar(datos_textos):
    """datos_textos: {clave: texto}. Devuelve [(Texto, texto, pt, interlineado_pt, x, centrado)] con las
    mismas reglas que tenía la plantilla: los que no caben se achican (el nombre y el lugar pasan a dos
    renglones), los montos van centrados en su columna y «PAGO COMPLETADO» en toda la fila."""
    import motor
    d = diseno()
    t = {k: Texto(v) for k, v in d["textos"].items()}
    salida = []
    for clave, texto in datos_textos.items():
        tx = t[clave]
        pt, inter, centro = tx.pt, None, None
        limite = motor.LIMITE_DERECHO.get(clave)
        if limite:
            x0 = tx.x
            w = tx.ancho(texto)
            if x0 + w > limite:
                factor = (limite - x0) / w
                if clave == "nombre_lugar" and factor < 0.8 and " | " in texto:
                    lineas = [p.strip() for p in texto.split(" | ", 1)]
                    texto = "\n".join(lineas)
                    factor = min(1.0, (limite - x0) / tx.ancho(texto))
                    pt = tx.pt * min(factor * 0.97, 1)
                    inter = pt * 1.15
                else:
                    pt = tx.pt * factor * 0.97
        if clave in ("reserva_monto", "saldo_monto"):
            centro = tx.centro_original()
        elif clave == "saldo" and texto == "PAGO COMPLETADO":
            centro = motor.CENTRO_PAGO_X
        elif tx.centrado:
            centro = tx.x
        salida.append((tx, texto, pt, inter, centro))
    return salida


def _pintar_texto(p, tx, texto, pt, inter, centro):
    px = tx.px(pt)
    paso = (inter or pt * 1.2) * PX_POR_PT * tx.sy
    for i, linea in enumerate(texto.split("\n")):
        w = ancho(tx.ps, linea, px) * tx.escala_h
        x = centro - w / 2 if centro is not None else tx.x
        _escribir(p, tx.ps, linea, x, tx.y + i * paso, px, tx.escala_h, tx.color)


# ================= Lista de servicios =================
def _renglones(items, s, g):
    """Renglones de la lista como los acomoda la plantilla (mismo texto y estilos que
    lista.texto_y_estilos): [(texto, estilo, interlineado_pt)] y el renglón donde empieza cada servicio."""
    L = lista.LEADING * s
    renglones, inicios = [("", "esp", L)], []
    for i, (titulo, detalle, _) in enumerate(items):
        ultimo = i == len(items) - 1
        inicios.append(len(renglones))
        renglones.append((titulo, "tit", L))
        if detalle:
            renglones.append((detalle, "det", L * lista.AIRE_DETALLE))
        if not ultimo:
            renglones.append(("", "esp", L * g))
    return renglones, inicios


def _lista(d, items):
    """Calcula la lista: renglones con su línea base (px de la hoja), íconos, rayas y rayitas."""
    items = [list(i) for i in items][:lista.MAX_SERVICIOS] or [["", "", lista.ICONO_POR_DEFECTO]]
    t = d["lista"]["transform"]
    k, x0, f = t[3], t[4], t[5]
    px_unidad = lista.LEADING * PX_POR_PT * k

    def medir(s, g):
        renglones, inicios = _renglones(items, s, g)
        y, filas, ancho_max = f, [], 0.0
        for i, (texto, estilo, inter) in enumerate(renglones):
            if i:
                y += inter * PX_POR_PT * k
            px = (lista.T_TITULO if estilo == "tit" else lista.T_DETALLE) * s * PX_POR_PT * k
            if estilo == "det":       # (Lemon Milk solo tiene mayúsculas)
                texto_m = texto
                w = ancho(FUENTE_DETALLE_LISTA, texto, px) + INCLINACION * px * 0.7
            elif estilo == "tit":
                texto_m = texto
                w = ancho(FUENTE_TITULO_LISTA, texto, px)
            else:
                texto_m, w = "", 0
            ancho_max = max(ancho_max, w)
            filas.append((texto_m, estilo, y, px))
        return filas, inicios, ancho_max

    s, g = lista.escala(items, f, px_unidad)
    filas, inicios, w = medir(s, g)
    if x0 + w > lista.LISTA_X_MAX:      # el renglón más largo no debe tocar el borde de la tarjeta
        s *= (lista.LISTA_X_MAX - x0) / w
        g = max(g, lista.relleno(items, f, px_unidad * s))
        filas, inicios, w = medir(s, g)
    y_items = [filas[i][2] for i in inicios]

    # Íconos: todos al mismo eje, del tamaño del texto y sin chocar con el de al lado
    meta = d["iconos"]
    si = min(1.05, s * 1.3)
    paso = min((b - a for a, b in zip(y_items, y_items[1:])), default=999)
    iconos = []
    for (_, _, icono), y in zip(items, y_items):
        icono = icono if icono in meta and f"icono_{icono}" in _piezas else lista.ICONO_POR_DEFECTO
        iw, ih = meta[icono]
        kk = min(si, 0.92 * paso / ih)
        cy = y + lista.AJUSTE_ICONO.get(icono, 0) * kk
        iconos.append((icono, QRectF(lista.ICONOS_CX - iw * kk / 2, cy - ih * kk / 2, iw * kk, ih * kk)))

    # Rayas entre servicios y tramos de rayitas junto a los íconos (como lista.comandos)
    tit_px, det_px = lista.T_TITULO * s * PX_POR_PT * k, lista.T_DETALLE * s * PX_POR_PT * k
    fines = []
    for i, (titulo, detalle, _) in enumerate(items):
        y_det = filas[inicios[i] + 1][2] if detalle else None
        fines.append(y_det + 0.24 * det_px if y_det else y_items[i] + 0.22 * tit_px)
    separadores = [round((fines[i] + y_items[i + 1] - 0.74 * tit_px) / 2) for i in range(len(items) - 1)]
    cortes = [lista.TITULOS_Y, *separadores, min(lista.TARJETA_LISTA[3] - lista.MARGEN, fines[-1] + 22)]
    tramos = [(a + 16, b - 16) for a, b in zip(cortes, cortes[1:])]
    return dict(x=x0, filas=filas, iconos=iconos, separadores=separadores, tramos=tramos, s=s)


_cache_lista = {}


def lista_calculada(items):
    clave = lista.clave(items)
    if clave not in _cache_lista:
        if len(_cache_lista) > 32:
            _cache_lista.clear()
        _cache_lista[clave] = _lista(diseno(), items)
    return _cache_lista[clave]


def _pintar_lista(p, L):
    x0, _, x1, _ = lista.TARJETA_LISTA
    p.setPen(QPen(QColor(226, 226, 226), 3, Qt.SolidLine, Qt.FlatCap))
    for y in L["separadores"]:
        p.drawLine(QPointF(x0 + lista.MARGEN, y + 0.5), QPointF(x1 - lista.MARGEN, y + 0.5))
    p.setPen(QPen(QColor(60, 60, 60), 4, Qt.SolidLine, Qt.FlatCap))
    x = lista.RAYITAS_X + 0.5
    for a, b in L["tramos"]:
        y = a
        while y < b:
            p.drawLine(QPointF(x, y), QPointF(x, min(y + 11, b)))
            y += 19
    for texto, estilo, y, px in L["filas"]:
        if estilo == "tit":
            _escribir(p, FUENTE_TITULO_LISTA, texto, L["x"], y, px, color="#000000")
        elif estilo == "det":
            _escribir(p, FUENTE_DETALLE_LISTA, texto, L["x"], y, px, color="#ff0000", inclinar=INCLINACION)
    for icono, r in L["iconos"]:
        p.drawImage(r, _piezas[f"icono_{icono}"])


# ================= El comprobante =================
def _pieza(p, nombre):
    x0, y0, _, _ = _diseno["piezas"][nombre]
    p.drawImage(QPointF(x0, y0), _piezas[nombre])


def _fondo(ancho_px):
    """El fondo del ancho pedido (se guarda: la vista en vivo pide siempre el mismo tamaño)."""
    with _candado:
        if ancho_px not in _fondos:
            original = _fondos[max(_fondos)]
            if len(_fondos) > 3:
                for w in [w for w in _fondos if w != original.width()]:
                    del _fondos[w]
            _fondos[ancho_px] = original.scaledToWidth(ancho_px, Qt.SmoothTransformation)
        return _fondos[ancho_px]


def dibujar(textos, items, captura=None, evento="BODA", completo=False, lado=None):
    """textos: {clave: texto} (fecha, tema, nombre_lugar, contacto, reserva, reserva_monto, saldo,
    saldo_monto). items: la lista de servicios. captura: QImage ya preparada (o None: queda el recuadro de
    ejemplo). lado: alto en px de la imagen (vista en vivo); sin él, del tamaño real de la hoja.
    Devuelve un QImage."""
    d = diseno()
    W, H = d["hoja"]
    k = min(1.0, lado / H) if lado else 1.0
    w, h = round(W * k), round(H * k)
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    p.drawImage(0, 0, _fondo(w))
    p.scale(w / W, h / H)
    if captura is not None and not captura.isNull():
        x, y, cw, ch = d["captura"]
        r = QRectF(x, y, cw, ch)
        camino = QPainterPath()
        camino.addRoundedRect(r, RADIO_CAPTURA, RADIO_CAPTURA)
        p.save()
        p.setClipPath(camino)
        p.drawImage(r, captura)
        p.restore()
    _pieza(p, "xv" if evento == "XV" else "boda")
    if not completo:
        _pieza(p, "raya_saldo")
    _pintar_lista(p, lista_calculada(items))
    for args in acomodar({c: t for c, t in textos.items() if t is not None}):
        _pintar_texto(p, *args)
    p.end()
    return img
