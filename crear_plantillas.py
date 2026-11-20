"""Crea la plantilla única del comprobante (PLANTILLAS/COMPROBANTE.psd) a partir del diseño base:
diseño «Tarjetas suaves», cabecera con foto, todos los íconos de servicios (ocultos, en su tamaño
natural) y la capa de rayas de la lista. La lista de cada comprobante la dibuja el programa
(lista.py); por eso cualquier paquete, con servicios agregados o quitados y con extras, sale de
esta misma plantilla. Junto a ella guarda COMPROBANTE.json (medidas que usa el programa) y la
VISTA PREVIA.jpg (con la lista del paquete Completo).

Uso:  python crear_plantillas.py
El PSD base nunca se modifica."""
import json
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import lista
import photocraft as motor   # (PhotoCraft: solo para crear la plantilla)
from lista import HOJA, IZQ, MARGEN, TARJETA_LISTA, TITULOS_Y

BASE = Path(__file__).resolve().parent
RECURSOS = BASE / "recursos"

# Ícono → capa del PSD base (nombre)
ICONOS_CAPA = {
    "camara": "Forma 1", "cobertura": "8bb2736703fabcee9d65d5c3e304704a", "video_fotos": "Forma 7",
    "album": "Forma 4", "video": "Forma 6", "usb": "288", "dron": "Forma 3", "cabina360": "Forma 5",
    "chispa": "108980",
}
# Íconos que no existen en el PSD: glifos negros sólidos de Segoe UI Symbol …
ICONOS_GLIFO = {"galeria": "🔗", "buzon": "☎", "enmarcada": "🖼",
                "video_largo": "🎬"}
# … y los de los extras, hechos con Higgsfield (recursos/icono_<clave>.png)
ICONOS_NUEVOS = ["cabina_fotos", "zancos", "telefono", "espejo", "backdrop", "cabezones"]

# Diseño «Tarjetas suaves»: fichas y tarjetas blancas con sombra suave (px de la hoja de 2480×3508).
# Ejes comunes: todo arranca en x = 300 (fichas, tarjetas y pago); separación de 40 entre tarjetas;
# margen interior de 45 en las tarjetas (títulos, rayas, íconos y marco de la captura).
NEGRO = (0, 0, 0, 255)
SEPARACION = 40
FICHA_FECHA = (IZQ, 920, 1200, 1140)
FICHA_CONTACTO = (1200 + SEPARACION, 920, 1960, 1140)
TEXTO_FICHA_X = 200          # el texto de la ficha empieza tras el ícono y la raya
RAYA_FICHA_X = 170           # raya de la ficha: a medio camino entre el ícono (40..140) y el texto
ESCALA_FICHAS = {"fecha": 0.85, "contacto": 0.88, "contacto_tit": 0.88}
DY_TEMA = -10                # bloque «TEMA»: su ícono arranca en el eje de los íconos (IZQ + MARGEN) y
                             # queda a la misma distancia de las fichas y de las tarjetas
TARJETA_CAPTURA = (1705 + SEPARACION, 1585, 2330, 2770)
MARCO_CAPTURA = (TARJETA_CAPTURA[0] + MARGEN, 1752, TARJETA_CAPTURA[2] - MARGEN, 2722)   # forma de pantalla
RADIO_MARCO = 30             # de celular (≈1:2): una captura del teléfono llena todo el marco
DX_LISTA = IZQ + MARGEN - 363                 # la lista arranca en el margen de la tarjeta
DY_LISTA = 24                # y baja un poco: aire bajo la raya de «DESCRIPCIÓN»
# Tarjeta de pago: simétrica respecto de la banda negra (filas, rayas y márgenes iguales arriba y abajo)
TARJETA_PAGO = (motor.CENTRO_PAGO_X - 885, 2810, motor.CENTRO_PAGO_X + 885, 3414)
BANDA_PAGO = (TARJETA_PAGO[0] + 50, 2982, TARJETA_PAGO[2] - 50, 3242)
COLUMNA_X = 1380             # raya entre la etiqueta y el monto («RESERVA CON:  |  Q600»)
FILA_RESERVA_Y, FILA_SALDO_Y = 2885, 3339     # centro de cada fila
RAYA_RESERVA_Y, RAYA_SALDO_Y = 2955, 3269     # rayas horizontales (del ancho de la banda)
ICONO_PAGO_ALTO = 96
ICONO_PAGO_CX = BANDA_PAGO[0] + 48            # billetera y reloj de arena: en el borde de la banda
ETIQUETA_PAGO_X = ICONO_PAGO_CX + 48 + 34     # las etiquetas empiezan tras su ícono
# Cabecera «foto cinematográfica» (Higgsfield): la forma negra se cambia por una foto oscura que se funde
# con la hoja; logo y píldora de contacto terminan en el borde derecho de las tarjetas y «COMPROBANTE»
# empieza en el izquierdo, a la altura de la píldora.
FOTO_CABECERA = RECURSOS / "cabecera_foto.jpg"
CABECERA_ALTO, CABECERA_FUNDIDO = 900, 640     # la foto llega a y = 900 y se funde con la hoja desde 640
DERECHA = 2330               # borde derecho común (tarjetas, logo y píldora de contacto)
PILDORA_Y, PILDORA_ALTO, PILDORA_AIRE = 544, 164, 60   # centro, alto y aire interior de la píldora
ICONOS_PAGO = {"reserva": RECURSOS / "icono_reserva.png", "saldo": RECURSOS / "icono_saldo.png"}  # de Higgsfield


def _pegar_icono(im, ruta, cx, cy, alto=ICONO_PAGO_ALTO):
    """Pega un ícono PNG (negro sobre transparente) centrado en (cx, cy) con el alto indicado."""
    with Image.open(ruta) as ic:
        ic = ic.convert("RGBA")
        ancho = round(ic.width * alto / ic.height)
        ic = ic.resize((ancho, alto), Image.LANCZOS)
    im.alpha_composite(ic, (round(cx - ancho / 2), round(cy - alto / 2)))


def _glifo_png(clave):
    RECURSOS.mkdir(exist_ok=True)
    ruta = RECURSOS / f"icono_{clave}.png"
    if not ruta.exists():
        f = ImageFont.truetype(r"C:\Windows\Fonts\seguisym.ttf", 400)
        im = Image.new("RGBA", (700, 700), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((50, 50), ICONOS_GLIFO[clave], font=f, fill=(0, 0, 0, 255))
        im.crop(im.getbbox()).save(ruta)
    return ruta


def _captura_ejemplo(ancho, alto):
    """Recuadro «AQUÍ VA LA CAPTURA DEL PAGO» con la proporción del marco."""
    W, H = round(ancho * 2), round(alto * 2)
    ruta = Path(tempfile.gettempdir()) / f"comprobante_captura_ejemplo_{W}x{H}.png"
    im = Image.new("RGB", (W, H), (244, 244, 244))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype("arialbd.ttf", 112)
    for i, t in enumerate(["AQUÍ VA LA", "CAPTURA", "DEL PAGO"]):
        w = d.textlength(t, font=f)
        d.text(((W - w) / 2, H / 2 - 210 + i * 145), t, font=f, fill=(165, 165, 165))
    im.save(ruta)
    return ruta


def _icono_calendario(t=88, k=4):
    """Calendario macizo con argollas y puntos (dibujado a 4× y reducido: bordes suaves)."""
    T = t * k
    im = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    g, arriba = 8 * k, 12 * k
    d.rounded_rectangle((g // 2, arriba, T - g // 2, T - g // 2), 16 * k, outline=NEGRO, width=g)
    d.rounded_rectangle((g // 2, arriba, T - g // 2, arriba + 26 * k), 16 * k, fill=NEGRO)
    d.rectangle((g // 2, arriba + 14 * k, T - g // 2, arriba + 26 * k), fill=NEGRO)
    for x in (0.3, 0.7):
        d.rounded_rectangle((T * x - 5 * k, 0, T * x + 5 * k, arriba + 12 * k), 5 * k, fill=NEGRO)
    r = 6 * k
    for y in (0.58, 0.79):
        for x in (0.3, 0.5, 0.7):
            d.ellipse((T * x - r, T * y - r, T * x + r, T * y + r), fill=NEGRO)
    return im.resize((t, t), Image.LANCZOS)


def _icono_telefono(t=88, k=4):
    """Auricular con ondas, del mismo peso que el calendario."""
    T = t * k
    im = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(r"C:\Windows\Fonts\SegoeIcons.ttf", int(T * 0.78))
    d.text((T * 0.04, T * 0.98), "\uE717", font=f, fill=NEGRO, anchor="ld", stroke_width=3 * k, stroke_fill=NEGRO)
    cx, cy = T * 0.6, T * 0.4
    for r in (0.2, 0.34):
        R = T * r
        d.arc((cx - R, cy - R, cx + R, cy + R), -90, 0, fill=NEGRO, width=int(6.5 * k))
    return im.resize((t, t), Image.LANCZOS)


def _hoja_png(dibujar, destino):
    """PNG del tamaño de la hoja. PhotoCraft recorta lo transparente al colocar una imagen: un punto
    casi invisible en dos esquinas conserva el tamaño y así la capa cae exacta en su lugar."""
    W, H = HOJA
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dibujar(im)
    im.putpixel((0, 0), (255, 255, 255, 1))
    im.putpixel((W - 1, H - 1), (255, 255, 255, 1))
    im.save(destino)
    return destino


def _tarjetas(destino):
    """Capa de fondo del diseño «Tarjetas suaves»: fichas de fecha y contacto (con ícono), tarjeta de
    la lista, tarjeta de la captura (con su marco),
    tarjeta del pago (banda negra, rayas y la raya de la fila de reserva). Va justo encima del patrón:
    los textos, íconos y fotos del diseño quedan por delante."""
    from PIL import ImageFilter
    W, H = HOJA
    cajas = [(FICHA_FECHA, 36), (FICHA_CONTACTO, 36), (TARJETA_LISTA, 44), (TARJETA_CAPTURA, 44),
             (TARJETA_PAGO, 44)]

    def dibujar(im):
        sombra = Image.new("L", (W, H), 0)
        ds = ImageDraw.Draw(sombra)
        for (x0, y0, x1, y1), r in cajas:
            ds.rounded_rectangle((x0 + 6, y0 + 14, x1 - 6, y1 + 14), r, fill=46)
        capa = Image.new("RGBA", (W, H), (20, 20, 20, 0))
        capa.putalpha(sombra.filter(ImageFilter.GaussianBlur(24)))
        im.alpha_composite(capa)
        d = ImageDraw.Draw(im)
        for caja, r in cajas:
            d.rounded_rectangle(caja, r, fill=(255, 255, 255, 255), outline=(234, 234, 234, 255), width=2)

        for (x0, y0, x1, y1), icono in ((FICHA_FECHA, _icono_calendario(100)),
                                        (FICHA_CONTACTO, _icono_telefono(100))):
            cy = (y0 + y1) // 2
            im.alpha_composite(icono, (x0 + 40, cy - icono.height // 2))
            xr = x0 + RAYA_FICHA_X
            d.line((xr, y0 + 52, xr, y1 - 52), fill=(40, 40, 40, 255), width=4)

        oscura = (60, 60, 60, 255)
        for x0, _, x1, _ in (TARJETA_LISTA, TARJETA_CAPTURA):
            d.line((x0 + MARGEN, TITULOS_Y, x1 - MARGEN, TITULOS_Y), fill=oscura, width=4)
        x0, y0, x1, y1 = MARCO_CAPTURA
        d.rounded_rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), RADIO_MARCO + 4, outline=(214, 214, 214, 255),
                            width=4)

        x0, _, x1, _ = BANDA_PAGO
        for y in (RAYA_RESERVA_Y, RAYA_SALDO_Y):
            d.line((x0, y, x1, y), fill=oscura, width=3)
        d.line((COLUMNA_X, FILA_RESERVA_Y - 34, COLUMNA_X, FILA_RESERVA_Y + 34), fill=oscura, width=4)
        d.rounded_rectangle(BANDA_PAGO, 44, fill=NEGRO)
        _pegar_icono(im, ICONOS_PAGO["reserva"], ICONO_PAGO_CX, FILA_RESERVA_Y)
    return _hoja_png(dibujar, destino)


def _raya_saldo(destino):
    """Reloj de arena y raya de la fila del saldo (capa aparte: se oculta con «PAGO COMPLETADO»)."""
    def dibujar(im):
        ImageDraw.Draw(im).line((COLUMNA_X, FILA_SALDO_Y - 34, COLUMNA_X, FILA_SALDO_Y + 34),
                                fill=(60, 60, 60, 255), width=4)
        _pegar_icono(im, ICONOS_PAGO["saldo"], ICONO_PAGO_CX, FILA_SALDO_Y)
    return _hoja_png(dibujar, destino)


def _titulo_cabecera(cfg, base, caja):
    """El título «COMPROBANTE» tal como se ve en el diseño base (su letra, Ethnocentric, no está instalada
    para PhotoCraft: si se mueve la capa de texto se redibuja con otra). Se toma de la imagen del PSD base:
    blanco sobre la forma negra → blanco con transparencia."""
    png = Path(tempfile.gettempdir()) / "comprobante_base.png"
    motor._cli(cfg, "convert", "--approve-high-memory", "--metadata", "none", base, str(png))
    x, y, w, h = caja
    with Image.open(png) as im:
        gris = im.convert("L").crop((x - 6, y - 6, x + w + 6, y + h + 6))
    png.unlink(missing_ok=True)
    titulo = Image.new("RGBA", gris.size, (255, 255, 255, 0))
    titulo.putalpha(gris.point(lambda v: max(0, min(255, round((v - 24) * 255 / 200)))))
    return titulo


def _cabecera(pildora, titulo, destino):
    """Foto de la cabecera (se funde suave con la hoja), la píldora translúcida del contacto y el título
    «COMPROBANTE» en el borde izquierdo común, a la altura de la píldora."""
    def dibujar(im):
        W = HOJA[0]
        foto = ImageOps.fit(Image.open(FOTO_CABECERA).convert("RGB"), (W, CABECERA_ALTO), Image.LANCZOS)
        alfa = Image.new("L", (W, CABECERA_ALTO), 255)
        d = ImageDraw.Draw(alfa)
        for y in range(CABECERA_FUNDIDO, CABECERA_ALTO):
            t = (y - CABECERA_FUNDIDO) / (CABECERA_ALTO - CABECERA_FUNDIDO)
            d.line((0, y, W, y), fill=round(255 * (1 - t * t * (3 - 2 * t))))
        foto.putalpha(alfa)
        im.alpha_composite(foto)
        capa = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(capa).rounded_rectangle(pildora, PILDORA_ALTO // 2, fill=(8, 8, 8, 170),
                                               outline=(255, 255, 255, 70), width=3)
        im.alpha_composite(capa)
        ancho_max = pildora[0] - 90 - IZQ + 12        # que no llegue a la píldora (90 px de aire)
        tit = titulo
        if tit.width > ancho_max:
            tit = tit.resize((ancho_max, round(tit.height * ancho_max / tit.width)), Image.LANCZOS)
        im.alpha_composite(tit, (IZQ - 6, PILDORA_Y - tit.height // 2))
    return _hoja_png(dibujar, destino)


def _marco_captura(destino):
    """Base redondeada donde se recorta la captura (máscara de recorte)."""
    def dibujar(im):
        ImageDraw.Draw(im).rounded_rectangle(MARCO_CAPTURA, RADIO_MARCO, fill=(255, 255, 255, 255))
    return _hoja_png(dibujar, destino)


def limpiar_xmp(psd):
    """Quita del XMP del PSD la lista de textos de capas (photoshop:TextLayers) y el historial de
    documentos de origen: ahí Photoshop deja textos viejos, por ejemplo nombres y teléfonos de clientes.
    Edita solo el recurso 1060 (XMP) de la sección «Image Resources»; el resto del archivo queda igual."""
    import re
    import struct
    datos = bytearray(Path(psd).read_bytes())
    if datos[:4] != b"8BPS":
        raise ValueError("No es un PSD")
    pos = 26
    pos += 4 + struct.unpack(">I", datos[pos:pos + 4])[0]          # color mode data
    ini_sec = pos
    largo_sec = struct.unpack(">I", datos[pos:pos + 4])[0]
    pos += 4
    fin_sec = pos + largo_sec
    while pos < fin_sec:
        if datos[pos:pos + 4] != b"8BIM":
            break
        rid = struct.unpack(">H", datos[pos + 4:pos + 6])[0]
        nlen = datos[pos + 6]
        nombre_total = 1 + nlen + ((1 + nlen) % 2)
        p_tam = pos + 6 + nombre_total
        tam = struct.unpack(">I", datos[p_tam:p_tam + 4])[0]
        p_dat = p_tam + 4
        fin_bloque = p_dat + tam + (tam % 2)
        if rid == 1060:
            xmp = datos[p_dat:p_dat + tam].decode("utf-8", "replace")
            for etiqueta in ("photoshop:TextLayers", "photoshop:DocumentAncestors"):
                xmp = re.sub(rf"\s*<{etiqueta}>.*?</{etiqueta}>", "", xmp, flags=re.S)
            nuevo = xmp.encode("utf-8")
            bloque = struct.pack(">I", len(nuevo)) + nuevo + (b"\0" if len(nuevo) % 2 else b"")
            datos[p_tam:fin_bloque] = bloque
            nuevo_largo = largo_sec + (len(bloque) - (fin_bloque - p_tam))
            datos[ini_sec:ini_sec + 4] = struct.pack(">I", nuevo_largo)
            Path(psd).write_bytes(bytes(datos))
            return True
        pos = fin_bloque
    return False


def _quad(cx, cy, w, h):
    x0, y0 = cx - w / 2, cy - h / 2
    return [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]


def _diseno_tarjetas(cfg, base, capas, loc, textos):
    """Comandos que pasan la plantilla al diseño «Tarjetas suaves»: capa de tarjetas; fecha y contacto
    en sus fichas; títulos «DESCRIPCIÓN» y «COMPROBANTE» en sus tarjetas; captura más grande, recortada
    con esquinas redondeadas y sin la sombra ni el borde viejos; tarjeta de pago con filas
    «etiqueta | monto» (el monto en su propia capa: RESERVA - MONTO, SALDO - MONTO), la banda negra
    adentro, billetera junto a la reserva y el reloj de arena y la raya del saldo aparte (RAYA - SALDO,
    se oculta con «PAGO COMPLETADO»)."""
    def buscar(cond):
        return [l for l in capas if l.get("bounds") and cond(l, *l["bounds"])]

    def texto(l):
        return ((l.get("text") or {}).get("text") or "").strip().upper() if l.get("kind") == "Type" else ""

    def forma(l):
        return l.get("kind") == "Shape"

    def centro(b):
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    contacto_tit = buscar(lambda l, *_: texto(l).startswith("CONTACTO"))[0]["id"]
    pago = buscar(lambda l, *_: texto(l).startswith("PAGO EXITOSO"))[0]["id"]
    titulos = buscar(lambda l, *_: texto(l).startswith("DESCRIPCI"))[0]["id"]
    tema_tit = buscar(lambda l, *_: texto(l) == "TEMA")[0]["id"]
    if len(loc["saldo"]) != 1:
        raise RuntimeError("El diseño base debe tener una sola capa «SALDO PENDIENTE».")
    saldo = loc["saldo"][0]
    captura = loc["captura"]["id"]
    bajo_captura = capas[next(i for i, l in enumerate(capas) if l["id"] == captura) + 1]["id"]
    ocultar = buscar(lambda l, x, y, w, h: forma(l) and (
        (h <= 8 and w > 1900)                                  # rayas bajo los títulos y sobre la reserva
        or (w > 1500 and h < 40 and y > 3300) or (x < 0 and y > 3200)   # raya y arco del pie
        or (w > 1800 and 250 < h < 400)                        # banda vieja de «PAGO EXITOSO»
        or (w < 120 and x > 2000 and 2875 < y < 3180)          # su adorno
        or (w <= 8 and h > 800)))                              # rayitas largas de la lista
    patron = next(l["id"] for l in capas if l.get("kind") == "Smart Object" and l.get("bounds")
                  and l["bounds"][2] >= HOJA[0] and l["bounds"][3] >= HOJA[1])


    # Medir los textos con su tamaño y contenido finales para ubicarlos
    reserva_et, reserva_monto = textos[loc["reserva"]].split(": ", 1)
    saldo_et, saldo_monto = textos[saldo].split(": ", 1)
    tam = {l["id"]: (l.get("text") or {}).get("sizePt") for l in capas}
    escalas = {loc["fecha"]: ESCALA_FICHAS["fecha"], loc["contacto"]: ESCALA_FICHAS["contacto"],
               contacto_tit: ESCALA_FICHAS["contacto_tit"]}
    previos = [("layer.setProps", {"layer": c, "locked": False})          # «CONTACTO :» viene bloqueada
               for c in (loc["fecha"], loc["contacto"], contacto_tit, loc["reserva"], saldo, pago, titulos,
                         tema_tit, loc["tema"], loc["nombre_lugar"], loc["icono_boda"], loc["icono_xv"]) if c]
    previos += [("type.setStyle", {"layer": c, "size": round(tam[c] * k, 4)}) for c, k in escalas.items()]
    previos.append(("type.setStyle", {"layer": loc["reserva"], "underline": False}))   # ya va en su fila
    seq = [("type.edit", {"layer": c, "text": txt}) for c, txt in textos.items()] + previos
    marcas = {}

    def medida(nombre, capa, txt=None):
        if txt is not None:
            seq.append(("type.edit", {"layer": capa, "text": txt}))
        marcas[nombre] = len(seq)
        seq.append(("type.edit", {"layer": capa, "move": [0, 0]}))
    for nombre, capa in (("fecha", loc["fecha"]), ("contacto", loc["contacto"]), ("contacto_tit", contacto_tit),
                         ("pago", pago), ("tema", loc["tema"]), ("tema_tit", tema_tit),
                         ("nombre_lugar", loc["nombre_lugar"])):
        medida(nombre, capa)
    for nombre, capa, txt in (("reserva_monto", loc["reserva"], reserva_monto),
                              ("reserva", loc["reserva"], reserva_et + ":"),
                              ("saldo_monto", saldo, saldo_monto), ("saldo", saldo, saldo_et + ":"),
                              ("comprobante", titulos, "comprobante"), ("descripcion", titulos, "Descripción")):
        medida(nombre, capa, txt)
    resultados = motor._medir_cli(cfg, base, seq)
    if len(resultados) != len(seq):
        raise RuntimeError(f"PhotoCraft devolvió {len(resultados)} resultados para {len(seq)} comandos.")
    caja = {n: resultados[i]["bounds"] for n, i in marcas.items()}    # [x0, y0, x1, y1]

    cmds = list(previos)

    def mover(capa, dx, dy):
        cmds.append(("type.edit", {**({"layer": capa} if capa else {}), "move": [round(dx, 1), round(dy, 1)]}))
    x0, y0, x1, y1 = FICHA_FECHA
    b = caja["fecha"]
    mover(loc["fecha"], x0 + TEXTO_FICHA_X - b[0], (y0 + y1) / 2 - centro(b)[1])
    x0, y0, x1, y1 = FICHA_CONTACTO
    dy = (y0 + y1) / 2 - (caja["contacto_tit"][1] + caja["contacto"][3]) / 2
    for nombre, capa in (("contacto_tit", contacto_tit), ("contacto", loc["contacto"])):
        mover(capa, x0 + TEXTO_FICHA_X - caja[nombre][0], dy)

    # Bloque «TEMA»: sus tres textos alineados entre sí y, con su ícono, corridos hacia el eje de íconos
    dx_tema = IZQ + MARGEN - next(l for l in capas if l["id"] == loc["icono_boda"])["bounds"][0]
    eje = caja["tema"][0] + dx_tema
    for nombre, capa in (("tema", loc["tema"]), ("tema_tit", tema_tit), ("nombre_lugar", loc["nombre_lugar"])):
        mover(capa, eje - caja[nombre][0], DY_TEMA)
    for icono in (loc["icono_boda"], loc["icono_xv"]):
        if icono:
            x, y, w, h = next(l for l in capas if l["id"] == icono)["bounds"]
            cmds.append(("edit.transform", {"layer": icono, "quad": _quad(x + w / 2 + dx_tema, y + h / 2 + DY_TEMA, w, h)}))

    # Títulos: «COMPROBANTE» pasa a su propia capa, centrada sobre la tarjeta de la captura
    cmds += [("type.edit", {"layer": titulos, "text": "comprobante"}),
             ("layer.duplicate", {"layer": titulos, "name": "TITULO - COMPROBANTE"}),
             ("layer.select", {"name": "TITULO - COMPROBANTE"})]
    mover(None, (TARJETA_CAPTURA[0] + TARJETA_CAPTURA[2]) / 2 - centro(caja["comprobante"])[0], 0)
    cmds.append(("type.edit", {"layer": titulos, "text": "Descripción"}))
    mover(titulos, TARJETA_LISTA[0] + MARGEN - caja["descripcion"][0], 0)   # al margen de la tarjeta

    # Tarjeta de pago: «etiqueta | monto» en cada fila y «PAGO EXITOSO» en el centro de la banda
    cx_monto = (COLUMNA_X + BANDA_PAGO[2]) / 2
    for nombre, capa, etiqueta, monto, fila_y, capa_monto in (
            ("reserva", loc["reserva"], reserva_et, reserva_monto, FILA_RESERVA_Y, "RESERVA - MONTO"),
            ("saldo", saldo, saldo_et, saldo_monto, FILA_SALDO_Y, "SALDO - MONTO")):
        bm, be = caja[nombre + "_monto"], caja[nombre]
        cmds += [("type.edit", {"layer": capa, "text": monto}),
                 ("layer.duplicate", {"layer": capa, "name": capa_monto}),
                 ("layer.select", {"name": capa_monto})]
        mover(None, cx_monto - centro(bm)[0], fila_y - centro(bm)[1])
        cmds.append(("type.edit", {"layer": capa, "text": etiqueta + ":"}))
        mover(capa, ETIQUETA_PAGO_X - be[0], fila_y - centro(be)[1])     # tras su ícono, a la izquierda
    bx, by = centro(caja["pago"])
    mover(pago, (BANDA_PAGO[0] + BANDA_PAGO[2]) / 2 - bx, (BANDA_PAGO[1] + BANDA_PAGO[3]) / 2 - by)

    # Cabecera: fuera la forma negra, los arcos, la píldora gris (y su lengüeta) y los círculos grises;
    # logo y contacto al borde derecho común, «COMPROBANTE» al izquierdo y a la altura de la píldora
    ocultar += buscar(lambda l, x, y, w, h: forma(l) and (
        (x <= 0 and y <= 0 and w > 2000 and h > 700) or (x < 0 and y < 0 and w < 1200)
        or (w > 1200 and 200 < h < 300 and y < 500) or (y < 420 and h < 100 and 150 < w < 300)
        or (x < 100 and 750 < y < 850 and h < 100)))
    contacto_cab = buscar(lambda l, x, y, w, h: y < 700 and x > 1200 and (
        (forma(l) and 80 < w < 110 and 80 < h < 110) or texto(l) == "GUATEMALA"
        or re.fullmatch(r"\d{4}-\d{4}", texto(l))))
    logo = buscar(lambda l, x, y, w, h: l.get("kind") == "Smart Object" and l.get("visible") and y < 400
                  and w > 800 and h < 300)
    titulo_cab = buscar(lambda l, x, y, w, h: texto(l) == "COMPROBANTE" and y < 800)
    if len(contacto_cab) != 4 or len(logo) != 1 or len(titulo_cab) != 1:
        raise RuntimeError("No se encontraron las capas de la cabecera (logo, título y contacto).")
    x_min = min(l["bounds"][0] for l in contacto_cab)
    x_max = max(l["bounds"][0] + l["bounds"][2] for l in contacto_cab)
    pildora = (DERECHA - (x_max - x_min) - 2 * PILDORA_AIRE, PILDORA_Y - PILDORA_ALTO // 2,
               DERECHA, PILDORA_Y + PILDORA_ALTO // 2)

    def trasladar(l, dx, dy=0):
        cmds.append(("layer.setProps", {"layer": l["id"], "locked": False}))
        x, y, w, h = l["bounds"]
        if l.get("kind") == "Type":
            mover(l["id"], dx, dy)
        else:
            cmds.append(("edit.transform", {"layer": l["id"], "quad": _quad(x + w / 2 + dx, y + h / 2 + dy, w, h)}))
    for l in contacto_cab:
        trasladar(l, DERECHA - PILDORA_AIRE - x_max)
    x, y, w, h = logo[0]["bounds"]
    trasladar(logo[0], DERECHA - (x + w))
    titulo = _titulo_cabecera(cfg, base, titulo_cab[0]["bounds"])   # va como imagen en la capa CABECERA
    ocultar.append(titulo_cab[0])

    cmds += [("layer.setProps", {"layer": l["id"], "visible": False}) for l in ocultar]

    # Capas nuevas: tarjetas (sobre el patrón), raya del saldo y la base redondeada de la captura
    W, H = HOJA
    tmp = Path(tempfile.gettempdir())

    def colocar(png, nombre, inteligente):
        return [("file.placeEmbedded", {"path": str(png), "smartObject": inteligente, "fit": False,
                                        "center": [W / 2, H / 2]}),
                ("edit.transform", {"quad": _quad(W / 2, H / 2, W, H)}),
                ("layer.setProps", {"name": nombre})]
    cmds.append(("layer.select", {"layer": patron}))
    # cabecera y tarjetas como capas de píxeles: no guardan además la imagen de origen (la plantilla debe
    # pesar menos de 100 MB, el máximo de GitHub por archivo)
    cmds += colocar(_cabecera(pildora, titulo, tmp / "comprobante_cabecera.png"), "CABECERA", False)
    cmds += colocar(_tarjetas(tmp / "comprobante_tarjetas.png"), "TARJETAS", False)
    cmds += colocar(lista.rayas_png([], [], tmp / "comprobante_rayas.png"), lista.CAPA_RAYAS, True)
    cmds += colocar(_raya_saldo(tmp / "comprobante_raya_saldo.png"), "RAYA - SALDO", False)
    cmds.append(("layer.select", {"layer": bajo_captura}))
    cmds += colocar(_marco_captura(tmp / "comprobante_marco_captura.png"), "MARCO - CAPTURA", False)
    cmds += [("layer.select", {"layer": captura}), ("layer.layerStyle.hideAllEffects", {}),
             ("layer.setProps", {"layer": captura, "clipped": True})]
    return cmds


def _png_icono(clave):
    """PNG negro sobre transparente de un ícono que no está en el PSD base (los de Higgsfield, reducidos:
    en el comprobante miden menos de 100 px y así la plantilla pesa menos)."""
    if clave in ICONOS_GLIFO:
        return _glifo_png(clave)
    destino = Path(tempfile.gettempdir()) / f"comprobante_icono_{clave}.png"
    with Image.open(RECURSOS / f"icono_{clave}.png") as im:
        im = im.convert("RGBA")
        im.thumbnail((240, 240), Image.LANCZOS)
        im.save(destino)
    return destino


def crear(cfg):
    base = cfg["plantilla_base"]
    if not Path(base).is_absolute():          # relativa a la carpeta PROGRAMA (DISEÑOS ORIGINALES/…)
        base = str(Path(__file__).resolve().parent / base)
    capas = motor._capas(cfg, base)
    loc = motor._localizar(capas)
    por_nombre = {l["name"]: l for l in capas}
    desc = next(l for l in capas if l.get("kind") == "Type" and l.get("bounds")
                and 1700 < l["bounds"][1] < 1800 and l["bounds"][3] > 300)
    destino = Path(motor.ruta_plantilla(cfg))
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir())

    # 1) Medidas de la capa de la lista ya en su lugar (las usa el programa en cada comprobante)
    t = motor._medir_cli(cfg, base, [("type.edit", {"layer": desc["id"], "move": [DX_LISTA, DY_LISTA]})])[-1]["transform"]
    meta = {"lista": {"d": t[3], "f": t[5]}, "iconos": {}}

    # 2) Plantilla: diseño, textos de ejemplo e íconos (todos ocultos, en su tamaño natural)
    args = ["run", base]

    def cmd(nombre, params=None):
        args.extend(["--cmd", nombre, "--params", json.dumps(params or {}, ensure_ascii=False)])

    cmd("type.edit", {"layer": desc["id"], "move": [DX_LISTA, DY_LISTA]})
    cmd("layer.setProps", {"layer": desc["id"], "name": lista.CAPA_LISTA})
    precio = cfg["paquetes"]["COMPLETO"]["precio"]
    reserva = cfg.get("reserva_por_defecto", 600)
    textos = {
        loc["fecha"]: "FECHA: 1/01/2026",
        loc["tema"]: "BODA (COMPLETO) - 1 DE ENERO",
        loc["nombre_lugar"]: "Nombre del festejado | Lugar",
        loc["contacto"]: "+502 0000 0000",
        loc["reserva"]: f"RESERVA CON: {motor.quetzales(reserva)}",
    }
    for c in loc["saldo"]:
        textos[c] = f"SALDO PENDIENTE: {motor.quetzales(precio - reserva)}"
    for capa, txt in textos.items():
        cmd("type.edit", {"layer": capa, "text": txt})
    for nombre, params in _diseno_tarjetas(cfg, base, capas, loc, textos):
        cmd(nombre, params)

    for icono, nombre in ICONOS_CAPA.items():
        capa = por_nombre[nombre]
        meta["iconos"][icono] = capa["bounds"][2:4]
        cmd("layer.setProps", {"layer": capa["id"], "name": lista.PREFIJO_ICONO + icono, "visible": False})
    for icono in [*ICONOS_GLIFO, *ICONOS_NUEVOS]:
        png = _png_icono(icono)
        with Image.open(png) as im:
            pw, ph = im.size
        if icono in ICONOS_GLIFO:
            ancho_max, alto_max = (118 if icono == "galeria" else 84), 64   # el enlace es ancho y bajo
        else:
            ancho_max, alto_max = 100, 82      # los de Higgsfield: algo más altos (zancos, espejo, cabezón)
        k = min(ancho_max / pw, alto_max / ph)
        meta["iconos"][icono] = [round(pw * k, 2), round(ph * k, 2)]
        cmd("layer.select", {"layer": desc["id"]})
        cmd("file.placeEmbedded", {"path": str(png), "smartObject": True, "fit": False,
                                   "center": [lista.ICONOS_CX, 2200]})
        cmd("edit.transform", {"quad": _quad(lista.ICONOS_CX, 2200, pw * k, ph * k)})
        cmd("layer.setProps", {"name": lista.PREFIJO_ICONO + icono, "visible": False})

    cx, cy, cx1, cy1 = MARCO_CAPTURA        # la captura, con forma de pantalla de celular
    cmd("layer.smartObjects.replaceContents",
        {"layer": loc["captura"]["id"], "path": str(_captura_ejemplo(cx1 - cx, cy1 - cy))})
    cmd("edit.transform", {"layer": loc["captura"]["id"], "quad": [[cx, cy], [cx1, cy], [cx1, cy1], [cx, cy1]]})

    intermedio = tmp / "comprobante_plantilla_sin_lista.psd"
    intermedio.unlink(missing_ok=True)
    args += ["--out", str(intermedio)]
    motor._cli(cfg, *args)
    destino.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # 3) Con la lista del paquete Completo, dibujada como en cada comprobante (así se ve la plantilla)
    capas2 = motor._capas(cfg, str(intermedio))
    cmds, s = lista.comandos(capas2, meta, cfg["paquetes"]["COMPLETO"]["incluye"],
                             lambda c: motor._medir_cli(cfg, str(intermedio), c), tmp)
    if destino.exists():
        destino.unlink()
    # sin la imagen combinada (la arma PhotoCraft desde las capas): ~25 MB menos, abre y guarda más rápido
    motor._cli(cfg, "run", str(intermedio), *motor._argumentos(cmds), "--out", str(destino),
               "--no-maximize-compatibility")
    intermedio.unlink(missing_ok=True)
    limpiar_xmp(destino)
    vista = destino.with_name("VISTA PREVIA.jpg")
    if vista.exists():
        vista.unlink()
    motor._cli(cfg, "convert", "--approve-high-memory", "--metadata", "none", str(destino), str(vista),
               "--quality", "85")
    return destino, s


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ruta, s = crear(motor.cargar_config())
    print(f"{ruta.name}  (lista del Completo al {s:.0%})")
