"""La lista de servicios del comprobante: se dibuja al generar cada comprobante (texto, íconos y rayas),
así cualquier paquete, con servicios agregados o quitados y con extras, sale de una sola plantilla.

Lo usan motor.py (en cada comprobante) y crear_plantillas.py (al armar la plantilla)."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

# ---- Geometría (px de la hoja de 2480×3508; diseño «Tarjetas suaves») ----
HOJA = (2480, 3508)
IZQ = 300                    # borde izquierdo común (fichas, tarjetas y pago)
MARGEN = 45                  # margen interior de las tarjetas
TITULOS_Y = 1716             # raya bajo «DESCRIPCIÓN» y «COMPROBANTE»
TARJETA_LISTA = (IZQ, 1585, 1705, 2770)
ICONOS_CX = IZQ + MARGEN + 84                 # un solo eje para todos los íconos de la lista
LISTA_X_MAX = TARJETA_LISTA[2] - MARGEN       # borde derecho de los renglones de la lista
RAYITAS_X = IZQ + MARGEN + 208                # rayitas entre íconos y textos (una tira por servicio)

# ---- Tipografía de la lista ----
LEADING = 16.43              # interlineado original (pt de la capa)
T_TITULO, T_DETALLE, T_ESPACIO = 32.865, 16.433, 8.0
LIMITE_INFERIOR = 2705       # última línea: termina a la altura del pie de la captura
AIRE_DETALLE = 1.06          # separación título → detalle (1 = original)
AIRE_MAX = 2.4               # aire máximo entre servicios cuando la lista es corta (1 = original)
PX_POR_PT = 4.1666667

# ---- Capas de la plantilla ----
CAPA_LISTA = "LISTA DEL PAQUETE"
CAPA_RAYAS = "LISTA - RAYAS"
PREFIJO_ICONO = "ICONO - "
# Ícono → ajuste vertical respecto de la línea del título (px a escala 1, del diseño original)
AJUSTE_ICONO = {"camara": 1.5, "cobertura": 9.5, "video_fotos": -9.5, "usb": 1.5, "dron": -18.5, "chispa": 1.5}
ICONO_POR_DEFECTO = "camara"   # para un servicio con un ícono que la plantilla no tiene
MAX_SERVICIOS = 14             # con más, la letra queda demasiado chica para leerse en el teléfono


def texto_y_estilos(items, s, g):
    """Texto de la lista y sus estilos (título negro GetVoIP, detalle rojo Lemon Milk en cursiva).
    Devuelve (texto, runs, inicio de cada servicio)."""
    tit = {"font": "GetVoIP Grotesque", "fontStyle": "Regular", "size": round(T_TITULO * s, 4),
           "color": "#000000", "fauxItalic": False, "leading": round(LEADING * s, 4)}
    det = {"font": "LEMON MILK", "fontStyle": "Bold", "size": round(T_DETALLE * s, 4),
           "color": "#ff0000", "fauxItalic": True, "leading": round(LEADING * s * AIRE_DETALLE, 4)}
    esp = {"font": "LEMON MILK", "fontStyle": "Bold", "size": round(T_ESPACIO * s, 4),
           "color": "#000000", "fauxItalic": False, "leading": round(LEADING * s * g, 4)}
    texto, runs, inicios = "", [], []

    def agregar(seg, estilo):
        nonlocal texto
        runs.append({"start": len(texto), "end": len(texto) + len(seg), **estilo})
        texto += seg

    agregar("\n", {**esp, "leading": round(LEADING * s, 4)})
    for i, (titulo, detalle, _) in enumerate(items):
        inicios.append(len(texto))
        ultimo = i == len(items) - 1
        agregar(titulo + ("" if ultimo and not detalle else "\n"), tit)
        if detalle:
            agregar(detalle + ("" if ultimo else "\n"), det)
        if not ultimo:
            agregar("\n", esp)
    return texto, runs, inicios


def _unidades(items, g):
    u = 1
    for i, (_, detalle, _) in enumerate(items):
        u += AIRE_DETALLE if detalle else 0
        if i < len(items) - 1:
            u += g + 1
    return u


def escala(items, y0, px_unidad):
    """(s, g): tamaño de la lista (1 = original) y aire entre servicios para que quepa en su tarjeta."""
    for g in (1.0, 0.85):
        s = min(1.0, (LIMITE_INFERIOR - y0) / (px_unidad * _unidades(items, g)))
        if s >= 0.85 or g == 0.85:
            break
    return s, max(g, relleno(items, y0, px_unidad * s))


def relleno(items, y0, px_unidad):
    """Aire entre servicios (g) para que una lista corta llegue hasta abajo de su tarjeta."""
    n = len(items)
    if n < 2:
        return 1.0
    return min(AIRE_MAX, ((LIMITE_INFERIOR - y0) / px_unidad - _unidades(items, 0)) / (n - 1))


def _quad(cx, cy, w, h):
    x0, y0 = cx - w / 2, cy - h / 2
    return [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]


def rayas_png(separadores, filas, destino):
    """Rayas entre servicios y rayitas junto a los íconos, en un PNG del tamaño de la hoja (un punto
    casi invisible en dos esquinas: PhotoCraft no lo recorta y la capa cae exacta en su lugar)."""
    W, H = HOJA
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, _, x1, _ = TARJETA_LISTA
    for y in separadores:
        d.line((x0 + MARGEN, y, x1 - MARGEN, y), fill=(226, 226, 226, 255), width=3)
    for a, b in filas:
        y = a
        while y < b:
            d.line((RAYITAS_X, y, RAYITAS_X, min(y + 11, b)), fill=(60, 60, 60, 255), width=4)
            y += 19
    im.putpixel((0, 0), (255, 255, 255, 1))
    im.putpixel((W - 1, H - 1), (255, 255, 255, 1))
    im.save(destino)
    return destino


def clave(items):
    """Identificador corto de una lista de servicios (para cachés y nombres de archivo)."""
    return hashlib.sha1(json.dumps(items, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def comandos(capas, meta, items, medir, carpeta_png):
    """Comandos de PhotoCraft que escriben la lista en la plantilla: texto, íconos (los que no van se
    ocultan; si uno se repite se duplica su capa) y la capa de rayas.
    meta: {"lista": {"d", "f"}, "iconos": {clave: [w, h]}} (lo guarda crear_plantillas junto a la
    plantilla). medir(cmds) → resultados (aplica los comandos a la plantilla sin guardar)."""
    items = [list(i) for i in items][:MAX_SERVICIOS] or [["", "", ICONO_POR_DEFECTO]]
    por_nombre = {l.get("name", ""): l for l in capas}
    capa_lista, capa_rayas = por_nombre[CAPA_LISTA]["id"], por_nombre[CAPA_RAYAS]["id"]
    iconos = {n[len(PREFIJO_ICONO):]: l for n, l in por_nombre.items() if n.startswith(PREFIJO_ICONO)}
    d, f = meta["lista"]["d"], meta["lista"]["f"]
    px_unidad = LEADING * PX_POR_PT * d

    s, g = escala(items, f, px_unidad)
    texto, runs, inicios = texto_y_estilos(items, s, g)
    res = medir([("type.edit", {"layer": capa_lista, "text": texto, "runs": runs})])[-1]
    x0, _, x1, _ = res["bounds"]
    if x1 > LISTA_X_MAX:                  # el renglón más largo no debe tocar el borde de la tarjeta
        s *= (LISTA_X_MAX - x0) / (x1 - x0)
        g = max(g, relleno(items, f, px_unidad * s))
        texto, runs, inicios = texto_y_estilos(items, s, g)
        res = medir([("type.edit", {"layer": capa_lista, "text": texto, "runs": runs})])[-1]
    t = res["transform"]
    linea = {ln["start"]: t[3] * ln["baseline"] + t[5] for ln in res["lines"]}
    y_items = [linea[i] for i in inicios]
    cmds = [("type.edit", {"layer": capa_lista, "text": texto, "runs": runs})]

    # Íconos: todos al mismo eje, del tamaño del texto y sin chocar con el de al lado
    si = min(1.05, s * 1.3)
    paso = min((b - a for a, b in zip(y_items, y_items[1:])), default=999)
    usados = {}
    for (_, _, icono), y in zip(items, y_items):
        icono = icono if icono in iconos and icono in meta["iconos"] else ICONO_POR_DEFECTO
        w, h = meta["iconos"][icono]
        k = min(si, 0.92 * paso / h)
        quad = _quad(ICONOS_CX, y + AJUSTE_ICONO.get(icono, 0) * k, w * k, h * k)
        n = usados.get(icono, 0)
        usados[icono] = n + 1
        if n == 0:
            cmds += [("layer.setProps", {"layer": iconos[icono]["id"], "visible": True}),
                     ("edit.transform", {"layer": iconos[icono]["id"], "quad": quad})]
        else:                             # el mismo ícono otra vez: una copia de su capa
            nombre = f"{PREFIJO_ICONO}{icono} #{n + 1}"
            cmds += [("layer.duplicate", {"layer": iconos[icono]["id"], "name": nombre}),
                     ("layer.select", {"name": nombre}), ("layer.setProps", {"visible": True}),
                     ("edit.transform", {"quad": quad})]
    cmds += [("layer.setProps", {"layer": l["id"], "visible": False}) for k_, l in iconos.items()
             if k_ not in usados]

    # Rayas entre servicios (a medio camino entre el final de uno y el título del siguiente) y tramos de
    # las rayitas junto a los íconos
    tit_px, det_px = T_TITULO * s * PX_POR_PT * t[3], T_DETALLE * s * PX_POR_PT * t[3]
    fines = []
    for i, (titulo, detalle, _) in enumerate(items):
        y_det = linea.get(inicios[i] + len(titulo) + 1) if detalle else None
        fines.append(y_det + 0.24 * det_px if y_det else y_items[i] + 0.22 * tit_px)
    separadores = [round((fines[i] + y_items[i + 1] - 0.74 * tit_px) / 2) for i in range(len(items) - 1)]
    cortes = [TITULOS_Y, *separadores, min(TARJETA_LISTA[3] - MARGEN, fines[-1] + 22)]
    filas = [(a + 16, b - 16) for a, b in zip(cortes, cortes[1:])]
    png = rayas_png(separadores, filas, Path(carpeta_png) / f"cinema_rayas_{clave(items)}.png")
    W, H = HOJA
    cmds += [("layer.smartObjects.replaceContents", {"layer": capa_rayas, "path": str(png)}),
             ("edit.transform", {"layer": capa_rayas, "quad": _quad(W / 2, H / 2, W, H)})]
    return cmds, s
