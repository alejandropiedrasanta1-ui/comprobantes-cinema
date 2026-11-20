"""Motor del generador: arma los textos del comprobante y lo dibuja (dibujo.py, sin PhotoCraft).
Guarda el JPG en la carpeta de salida; la vista en vivo se dibuja en memoria del tamaño de la pantalla."""
import json
import os
import re
import threading
from datetime import date
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

import dibujo
import rutas

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
CONFIG_USUARIO = rutas.CONFIG_USUARIO


def _fusionar(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fusionar(base[k], v)
        else:
            base[k] = v
    return base


def cargar_config():
    """Configuración incluida + preferencias del usuario (carpeta de salida, precios, apariencia)."""
    with open(rutas.recurso("config_default.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if CONFIG_USUARIO.exists():
        try:
            with open(CONFIG_USUARIO, encoding="utf-8") as f:
                _fusionar(cfg, json.load(f))
        except (OSError, ValueError):
            pass
    if cfg.get("carpeta_salida") in (None, "", "auto"):
        cfg["carpeta_salida"] = str(rutas.SALIDA_POR_DEFECTO)
    return cfg


def guardar_preferencia(clave, valor):
    datos = {}
    if CONFIG_USUARIO.exists():
        try:
            datos = json.loads(CONFIG_USUARIO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            datos = {}
    datos[clave] = valor
    CONFIG_USUARIO.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_USUARIO.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def servicios(cfg, datos):
    """Servicios que van en el comprobante: los indicados en datos["servicios"] (el paquete con sus
    cambios y los extras del cliente) o, si no vienen, los del paquete."""
    return [list(s) for s in (datos.get("servicios") or cfg["paquetes"][datos["paquete"]].get("incluye", []))]


def item_extra(extra, opcion):
    """Renglón de la lista para un extra con la opción elegida: [título, (opción), ícono]."""
    return [extra["titulo"], f"({extra['opciones'][opcion][0]})", extra["icono"]]


def precio_extra(extra, opcion):
    return float(extra["opciones"][opcion][1])


def precio_item(cfg, item):
    """Precio de un renglón si es un extra del catálogo con una de sus opciones (0 si no lo es)."""
    for extra in cfg.get("extras", []):
        for i in range(len(extra["opciones"])):
            if list(item[:2]) == item_extra(extra, i)[:2]:
                return precio_extra(extra, i)
    return 0.0


def con_extras(incluye, extras):
    """La lista del paquete con los extras del cliente: van antes de «Memoria USB y link» (la entrega
    queda al final, como en los paquetes)."""
    incluye, extras = [list(i) for i in incluye], [list(e) for e in extras]
    if incluye and incluye[-1][2] == "usb":
        return incluye[:-1] + extras + incluye[-1:]
    return incluye + extras


def config_por_defecto():
    """config_default.json tal cual (sin las preferencias del usuario): para «Restablecer»."""
    with open(rutas.recurso("config_default.json"), encoding="utf-8") as f:
        return json.load(f)


def quetzales(valor):
    valor = float(valor)
    return f"Q{valor:,.0f}" if valor.is_integer() else f"Q{valor:,.2f}"


# Borde derecho máximo (px) de los textos que pueden crecer: así no se salen de la hoja
# ni chocan con el dron.
LIMITE_DERECHO = {"tema": 2330, "nombre_lugar": 2330, "contacto": 1930,   # tema: hasta el borde de las
                  "fecha": 1175}                     # tarjetas; fecha y contacto: dentro de su ficha
# Centro (px) de la tarjeta de pago: ahí va «PAGO COMPLETADO» cuando ya no hay saldo (sin monto ni raya)
CENTRO_PAGO_X = 1185


def _recortar_bordes(im, tolerancia=18):
    """Quita los bordes lisos alrededor de la imagen (barras negras, márgenes blancos de una foto
    recortada): así la captura aprovecha todo el marco. Solo recorta si queda la mayor parte."""
    fondo = Image.new("RGB", im.size, im.getpixel((0, 0)))
    caja = ImageChops.difference(im, fondo).convert("L").point(lambda v: 255 if v > tolerancia else 0).getbbox()
    if caja and (caja[2] - caja[0]) * (caja[3] - caja[1]) >= 0.5 * im.width * im.height:
        return im.crop(caja)
    return im


def _preparar_captura(ruta, ancho_marco, alto_marco, destino=None):
    """Llena todo el marco con la captura, sin deformarla y sin bandas vacías:
    - si su forma se parece a la del marco (±15 %: las capturas de celular, el marco tiene su forma), la
      recorta apenas para cubrirlo (se pierden la barra de estado y la de abajo);
    - si no (p. ej. la captura alta de un celular), va completa al centro, a todo lo alto o ancho,
      sobre una copia ampliada, desenfocada y oscurecida de sí misma que cubre el resto del marco."""
    im = _recortar_bordes(ImageOps.exif_transpose(Image.open(ruta)).convert("RGB"))
    W, H = round(ancho_marco * 2), round(alto_marco * 2)     # el doble del marco: nítida al imprimir
    prop, prop_im = W / H, im.width / im.height
    if abs(prop_im / prop - 1) <= 0.15:
        im = ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.4))
        if destino:
            im.save(destino)
        return im
    fondo = ImageOps.fit(im, (W // 4, H // 4), Image.LANCZOS)
    fondo = fondo.filter(ImageFilter.GaussianBlur(W / 60)).resize((W, H), Image.LANCZOS)
    fondo = ImageEnhance.Brightness(ImageEnhance.Color(fondo).enhance(0.7)).enhance(0.55)
    k = min(W / im.width, H / im.height)
    frente = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    x, y = (W - frente.width) // 2, (H - frente.height) // 2
    sombra = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sombra).rectangle((x, y, x + frente.width, y + frente.height), fill=150)
    fondo = Image.composite(Image.new("RGB", (W, H)), fondo, sombra.filter(ImageFilter.GaussianBlur(W / 70)))
    fondo.paste(frente, (x, y))
    if destino:
        fondo.save(destino)
    return fondo


def _nombre_archivo(carpeta, base):
    base = re.sub(r'[<>:"/\\|?*]+', "", base).strip() or "COMPROBANTE"
    ruta = carpeta / f"{base}.jpg"
    n = 2
    while ruta.exists():
        ruta = carpeta / f"{base} ({n}).jpg"
        n += 1
    return ruta


CONCEPTOS = {"RESERVA CON": "RESERVA", "ABONO": "ABONO", "PAGO FINAL": "PAGO FINAL"}


def _textos(datos, cfg):
    """Los textos del comprobante, la clave del evento (BODA o XV) y si ya no queda saldo."""
    evento = cfg["eventos"].get(datos["evento"], datos["evento"]).upper()
    fe: date = datos["fecha_evento"]
    fc: date = datos["fecha_comprobante"]
    monto = float(datos.get("monto", datos.get("reserva", 0)))
    concepto = datos.get("concepto", "RESERVA CON")
    saldo = float(datos["saldo"]) if "saldo" in datos else max(float(datos["total"]) - monto, 0)
    completo = saldo <= 0
    textos = {
        "fecha": f"FECHA: {fc.day}/{fc.month:02d}/{fc.year}",
        "tema": f"{evento} ({datos['paquete']}) - {fe.day} DE {MESES[fe.month - 1]}",
        "nombre_lugar": f"{datos['festejado'].strip()} | {datos['lugar'].strip()}",
        "contacto": datos["contacto"].strip(),
        "reserva": f"{concepto}:",
        "reserva_monto": quetzales(monto),
        "saldo": "PAGO COMPLETADO" if completo else "SALDO PENDIENTE:",
        "saldo_monto": None if completo else quetzales(saldo),
    }
    return textos, evento, completo, concepto


def _a_qimage(im):
    from PySide6.QtGui import QImage
    im = im.convert("RGB")
    return QImage(im.tobytes("raw", "RGB"), im.width, im.height, 3 * im.width, QImage.Format_RGB888).copy()


_candado_captura = threading.Lock()
_ultima_captura = [None, None]   # [clave, QImage] de la captura ya preparada (la vista se repite en cada tecla)


def _captura(ruta):
    """La captura del pago lista para el marco (QImage), preparada una sola vez mientras sea la misma."""
    _, _, w, h = dibujo.diseno()["captura"]
    st = os.stat(ruta)
    clave = (str(ruta), st.st_mtime, st.st_size, w, h)
    with _candado_captura:
        if _ultima_captura[0] != clave:
            _ultima_captura[:] = [clave, _a_qimage(_preparar_captura(ruta, w, h))]
        return _ultima_captura[1]


def dibujar(datos, cfg=None, lado=None):
    """El comprobante como QImage (lado: alto en px para la vista en vivo; sin él, tamaño real)."""
    cfg = cfg or cargar_config()
    textos, evento, completo, _ = _textos(datos, cfg)
    captura = _captura(datos["captura"]) if datos.get("captura") else None
    return dibujo.dibujar(textos, servicios(cfg, datos), captura, evento, completo, lado)


def generar(datos, cfg=None, destino=None, calidad=None, lado=None):
    """datos: evento, paquete, festejado, lugar, fecha_evento (date), fecha_comprobante (date),
    contacto, total, monto (o reserva), captura (ruta de imagen).
    Opcionales: concepto ("RESERVA CON", "ABONO", "PAGO FINAL"), saldo (lo que falta después
    de este pago; si no se da, total - monto) y servicios ([[título, detalle, ícono], …]: el paquete
    con sus cambios y los extras; si no se da, los del paquete). Devuelve la ruta del JPG.
    destino: archivo a escribir (si no, uno nuevo en la carpeta de salida); lado: alto de la imagen."""
    cfg = cfg or cargar_config()
    textos, evento, _, concepto = _textos(datos, cfg)
    fe = datos["fecha_evento"]
    if destino:
        destino = Path(destino)
        calidad = calidad or 80
    else:
        salida = Path(cfg["carpeta_salida"])
        salida.mkdir(parents=True, exist_ok=True)
        destino = _nombre_archivo(
            salida, f"COMPROBANTE - {evento} {datos['paquete']} - {datos['festejado'].strip()} - "
                    f"{fe.day:02d}-{fe.month:02d}-{fe.year} - {CONCEPTOS.get(concepto, concepto)}")
    calidad = calidad or cfg.get("calidad_jpg", 92)
    guardar_jpg(dibujar(datos, cfg, lado), destino, calidad)
    return destino


def guardar_jpg(img, destino, calidad=92):
    """Guarda un QImage como JPG con Pillow (≈4 veces más rápido que el de Qt, misma calidad: color sin
    submuestreo, así el rojo de la lista queda nítido). Sin metadatos: no quedan rutas ni datos viejos."""
    from PySide6.QtGui import QImage
    rgb = img.convertToFormat(QImage.Format_RGB888)
    im = Image.frombuffer("RGB", (rgb.width(), rgb.height()), bytes(rgb.constBits()), "raw", "RGB",
                          rgb.bytesPerLine(), 1)
    try:
        im.save(destino, "JPEG", quality=int(calidad), subsampling=0)
    except OSError as e:
        raise RuntimeError(f"No se pudo guardar el comprobante en:\n{destino}\n\n{e}")


def generar_vista(datos, cfg, lado):
    """Vista en vivo: el comprobante en memoria, del tamaño de la pantalla (QImage)."""
    return dibujar(datos, cfg, lado)
