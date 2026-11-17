"""Crea las plantillas PSD de cada paquete (ESENCIAL, INTERMEDIO, COMPLETO, PREMIUM) a partir
del diseño base, con la lista de servicios y los íconos de config.json.

Uso:  python crear_plantillas.py            -> crea las 4
      python crear_plantillas.py PREMIUM    -> crea solo esa
Para cambiar lo que incluye un paquete, edita "incluye" en config_default.json y vuelve a ejecutarlo.
El PSD base nunca se modifica."""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import motor

BASE = Path(__file__).resolve().parent
RECURSOS = BASE / "recursos"

# Ícono -> capa del PSD base (nombre) y ajuste vertical del diseño original (px a escala 1)
ICONOS_CAPA = {
    "camara": ("Forma 1", 1.5), "cobertura": ("8bb2736703fabcee9d65d5c3e304704a", 9.5),
    "video_fotos": ("Forma 7", -9.5), "album": ("Forma 4", 0), "video": ("Forma 6", 0),
    "usb": ("288", 1.5), "dron": ("Forma 3", -18.5), "cabina360": ("Forma 5", 0),
    "chispa": ("108980", 1.5),
}
# Íconos que no existen en el PSD: glifos negros sólidos de Segoe UI Symbol
ICONOS_GLIFO = {"galeria": "\U0001F517", "buzon": "\u260E", "enmarcada": "\U0001F5BC",
                "video_largo": "\U0001F3AC"}

LEADING = 16.43            # interlineado original (pt de la capa)
T_TITULO, T_DETALLE, T_ESPACIO = 32.865, 16.433, 8.0
CENTRO_ICONOS_X = 493       # centro de la columna de íconos
BORDE_DER_CAMARA = 531      # el ícono doble (cámara + video) se alinea a la derecha
LIMITE_INFERIOR = 2660      # última línea de la lista (antes de la raya y "RESERVA CON")
AIRE_DETALLE = 1.06         # separación título -> detalle (1 = original)


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
    RECURSOS.mkdir(exist_ok=True)
    ruta = RECURSOS / "captura_ejemplo.png"
    if not ruta.exists():
        W, H = ancho * 2, alto * 2
        im = Image.new("RGB", (W, H), (244, 244, 244))
        d = ImageDraw.Draw(im)
        f = ImageFont.truetype("arialbd.ttf", 70)
        for i, t in enumerate(["AQUÍ VA LA", "CAPTURA", "DEL PAGO"]):
            w = d.textlength(t, font=f)
            d.text(((W - w) / 2, H / 2 - 130 + i * 90), t, font=f, fill=(170, 170, 170))
        im.save(ruta)
    return ruta


def _lista(items, s, g):
    """Texto de la lista y sus estilos (título negro GetVoIP, detalle rojo Lemon Milk en cursiva)."""
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


def _escala(items, y0, px_por_unidad):
    """Tamaño de la lista para que quepa en el área de descripción (1 = tamaño original)."""
    def unidades(g):
        u = 1
        for i, (_, detalle, _) in enumerate(items):
            u += AIRE_DETALLE if detalle else 0
            if i < len(items) - 1:
                u += g + 1
        return u
    for g in (1.0, 0.85):
        s = min(1.0, (LIMITE_INFERIOR - y0) / (px_por_unidad * unidades(g)))
        if s >= 0.85 or g == 0.85:
            return s, g


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


def crear(clave, cfg):
    paquete = cfg["paquetes"][clave]
    items = paquete["incluye"]
    base = cfg["plantilla_base"]
    if not Path(base).is_absolute():          # relativa a la carpeta PROGRAMA (DISEÑOS ORIGINALES/…)
        base = str(Path(__file__).resolve().parent / base)
    capas = motor._capas(cfg, base)
    loc = motor._localizar(capas)
    por_nombre = {l["name"]: l for l in capas}
    desc = next(l for l in capas if l.get("kind") == "Type" and l.get("bounds")
                and 1700 < l["bounds"][1] < 1800 and l["bounds"][3] > 300)

    # 1) Medir: escribir la lista y leer dónde cae cada línea
    a, _, _, d, _, f = json.loads(next(
        ln for ln in motor._cli(cfg, "run", base, "--cmd", "type.edit", "--params",
                                json.dumps({"layer": desc["id"], "move": [0, 0]})).splitlines()
        if ln.startswith("{")))["result"]["transform"]
    s, g = _escala(items, f, LEADING * 4.1666667 * d)
    texto, runs, inicios = _lista(items, s, g)
    res = json.loads(next(
        ln for ln in motor._cli(cfg, "run", base, "--cmd", "type.edit", "--params",
                                json.dumps({"layer": desc["id"], "text": texto, "runs": runs},
                                           ensure_ascii=False)).splitlines()
        if ln.startswith("{")))["result"]
    t = res["transform"]
    base_linea = {ln["start"]: t[3] * ln["baseline"] + t[5] for ln in res["lines"]}
    y_items = [base_linea[i] for i in inicios]
    si = min(1.0, s * 1.15)  # escala de los íconos
    paso = min((b - a for a, b in zip(y_items, y_items[1:])), default=999)

    # 2) Construir la plantilla
    args = ["run", base]

    def cmd(nombre, params=None):
        args.extend(["--cmd", nombre, "--params", json.dumps(params or {}, ensure_ascii=False)])

    cmd("type.edit", {"layer": desc["id"], "text": texto, "runs": runs})
    cmd("layer.setProps", {"layer": desc["id"], "name": "LISTA DEL PAQUETE"})
    precio = paquete["precio"]
    reserva = cfg.get("reserva_por_defecto", 600)
    textos = {
        loc["fecha"]: "FECHA: 1/01/2026",
        loc["tema"]: f"BODA({clave}) - 1 DE ENERO",
        loc["nombre_lugar"]: "Nombre del festejado | Lugar",
        loc["contacto"]: "+502 0000 0000",
        loc["reserva"]: f"RESERVA CON: {motor.quetzales(reserva)}",
    }
    for c in loc["saldo"]:
        textos[c] = f"SALDO PENDIENTE: {motor.quetzales(precio - reserva)}"
    for capa, txt in textos.items():
        cmd("type.edit", {"layer": capa, "text": txt})

    usados = {icono: y for (_, _, icono), y in zip(items, y_items)}
    for icono, (nombre, ajuste_y) in ICONOS_CAPA.items():
        capa = por_nombre[nombre]
        if icono not in usados:
            cmd("layer.setProps", {"layer": capa["id"], "visible": False})
            continue
        x, y, w, h = capa["bounds"]
        k = min(si, 0.92 * paso / h)  # que no choque con el ícono de al lado
        cx = BORDE_DER_CAMARA - w * k / 2 if icono == "camara" else x + w / 2
        cmd("layer.setProps", {"layer": capa["id"], "visible": True})
        cmd("edit.transform", {"layer": capa["id"],
                               "quad": _quad(cx, usados[icono] + ajuste_y * k, w * k, h * k)})
    for icono in ICONOS_GLIFO:
        if icono not in usados:
            continue
        png = _glifo_png(icono)
        with Image.open(png) as im:
            pw, ph = im.size
        ancho_max = 118 if icono == "galeria" else 84  # el enlace es ancho y bajo
        k = min(ancho_max * si / pw, 64 * si / ph)
        cmd("layer.select", {"layer": desc["id"]})
        cmd("file.placeEmbedded", {"path": str(png), "smartObject": True, "fit": False,
                                   "center": [CENTRO_ICONOS_X, usados[icono]]})
        cmd("edit.transform", {"quad": _quad(CENTRO_ICONOS_X, usados[icono], pw * k, ph * k)})
        cmd("layer.setProps", {"name": f"ICONO - {icono}"})

    cx, cy, cw, ch = loc["captura"]["bounds"]
    cmd("layer.smartObjects.replaceContents",
        {"layer": loc["captura"]["id"], "path": str(_captura_ejemplo(cw, ch))})
    cmd("edit.transform", {"layer": loc["captura"]["id"],
                           "quad": [[cx, cy], [cx + cw, cy], [cx + cw, cy + ch], [cx, cy + ch]]})

    destino = Path(motor.ruta_plantilla(paquete))
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()
    args += ["--out", str(destino)]
    motor._cli(cfg, *args)
    limpiar_xmp(destino)
    vista = destino.with_name(f"VISTA PREVIA - {clave}.jpg")
    if vista.exists():
        vista.unlink()
    motor._cli(cfg, "convert", "--approve-high-memory", "--metadata", "none", str(destino), str(vista),
               "--quality", "85")
    return destino, s


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = motor.cargar_config()
    claves = [a.upper() for a in sys.argv[1:]] or list(cfg["paquetes"])
    for clave in claves:
        ruta, s = crear(clave, cfg)
        print(f"{clave}: {ruta.name}  (texto al {s:.0%})")
