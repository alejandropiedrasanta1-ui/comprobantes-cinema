"""Motor del generador: abre la plantilla PSD con PhotoCraft (sin ventana),
cambia los textos, coloca la captura del pago y exporta un JPG.
Las plantillas originales nunca se modifican."""
import atexit
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

import lista
import rutas

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CONFIG_USUARIO = rutas.CONFIG_USUARIO


def buscar_photocraft():
    """Ubica photocraft-cli en las carpetas habituales de Windows y Mac."""
    candidatos = []
    if rutas.ES_WINDOWS:
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            if base:
                candidatos += [os.path.join(base, "ArtCraft", "PhotoCraft", "photocraft-cli.exe"),
                               os.path.join(base, "PhotoCraft", "photocraft-cli.exe")]
    elif rutas.ES_MAC:
        for apps in ("/Applications", os.path.expanduser("~/Applications")):
            candidatos += glob.glob(f"{apps}/*.app/Contents/*/photocraft-cli")
            candidatos += glob.glob(f"{apps}/*/*.app/Contents/*/photocraft-cli")
    candidatos.append(shutil.which("photocraft-cli") or "")
    return next((c for c in candidatos if c and os.path.isfile(c)), None)


def _fusionar(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fusionar(base[k], v)
        else:
            base[k] = v
    return base


def cargar_config():
    """Configuración incluida + preferencias del usuario (PhotoCraft, carpeta de salida, precios)."""
    with open(rutas.recurso("config_default.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if CONFIG_USUARIO.exists():
        try:
            with open(CONFIG_USUARIO, encoding="utf-8") as f:
                _fusionar(cfg, json.load(f))
        except (OSError, ValueError):
            pass
    if not os.path.isfile(cfg.get("photocraft_cli") or ""):
        cfg["photocraft_cli"] = buscar_photocraft() or ""
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


def ruta_plantilla(cfg):
    """La plantilla única del comprobante (la lista de servicios se dibuja en cada comprobante)."""
    return str(rutas.recurso(cfg.get("plantilla") or "PLANTILLAS/COMPROBANTE.psd"))


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


_cache_meta = {}


def _meta_plantilla(plantilla):
    """Datos que crear_plantillas guarda junto a la plantilla (medidas de la lista y de cada ícono)."""
    archivo = Path(plantilla).with_suffix(".json")
    st = archivo.stat()
    clave = (str(archivo), st.st_mtime, st.st_size)
    if clave not in _cache_meta:
        _cache_meta[clave] = json.loads(archivo.read_text(encoding="utf-8"))
    return _cache_meta[clave]


_cache_lista = {}


def _comandos_lista(cfg, plantilla, capas, items, medir):
    """Comandos que escriben la lista en la plantilla (medida una sola vez por lista: en la vista en vivo
    no se vuelve a medir en cada tecla y el comprobante final reutiliza lo de la vista)."""
    st = os.stat(plantilla)
    clave = (plantilla, st.st_mtime, st.st_size, lista.clave(items))
    if clave not in _cache_lista:
        cmds, _ = lista.comandos(capas, _meta_plantilla(plantilla), items, medir, tempfile.gettempdir())
        _cache_lista[clave] = cmds
    return clave[3], _cache_lista[clave]


def quetzales(valor):
    valor = float(valor)
    return f"Q{valor:,.0f}" if valor.is_integer() else f"Q{valor:,.2f}"


def _cli(cfg, *args):
    exe = cfg.get("photocraft_cli") or ""
    if not os.path.isfile(exe):
        raise RuntimeError("No se encontró PhotoCraft (photocraft-cli).\n"
                           "Instálalo o indica dónde está con el botón «PhotoCraft…».")
    args = list(args)
    if args and args[0] in ("run", "info"):
        # Las plantillas pesan ~90 MB: sin esto PhotoCraft las rechaza cuando la PC tiene poca RAM libre.
        args.insert(1, "--approve-high-memory")
    for intento in range(2):
        r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", creationflags=SIN_VENTANA)
        salida = (r.stderr or r.stdout).strip()
        if r.returncode == 0 or "memory" not in salida.lower() or intento:
            break
        time.sleep(4)  # la falta de memoria suele ser un pico momentáneo: se reintenta una vez
    if r.returncode != 0:
        if "memory" in salida.lower():
            raise RuntimeError("No hay suficiente memoria libre para abrir la plantilla.\n"
                               "Cierra programas pesados (DaVinci Resolve, Premiere, Chrome…) "
                               "y vuelve a intentar.\n\nDetalle: " + salida.splitlines()[-1][:200])
        raise RuntimeError("PhotoCraft no pudo generar la imagen:\n" + "\n".join(salida.splitlines()[-5:]))
    return r.stdout


_cache_capas = {}


def _capas(cfg, plantilla):
    """Lee el árbol de capas de la plantilla (en caché mientras el PSD no cambie). La caché también
    se guarda en disco: así al abrir el programa no se vuelve a leer el PSD (~90 MB) solo para esto."""
    st = os.stat(plantilla)
    clave = (plantilla, st.st_mtime, st.st_size)
    if clave not in _cache_capas:
        carpeta = Path(CONFIG_USUARIO).parent / "cache"
        nombre = f"capas - {Path(plantilla).stem}"
        archivo = carpeta / f"{nombre} - {int(st.st_mtime)}-{st.st_size}.json"
        try:
            planas = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = json.loads(_cli(cfg, "info", "--compact", plantilla))
            planas = []

            def recorrer(ls):
                for l in ls:
                    planas.append(l)
                    recorrer(l.get("children") or [])
            recorrer(info["layers"])
            try:
                carpeta.mkdir(parents=True, exist_ok=True)
                for viejo in carpeta.glob(f"{glob.escape(nombre)} - *.json"):  # de versiones anteriores del PSD
                    viejo.unlink(missing_ok=True)
                archivo.write_text(json.dumps(planas, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        _cache_capas[clave] = planas
    return _cache_capas[clave]


def _localizar(capas):
    """Ubica las capas a editar por su contenido, así funciona aunque se edite el PSD."""
    loc = {"saldo": [], "icono_boda": None, "icono_xv": None, "captura": None,
           "reserva_monto": None, "saldo_monto": None, "raya_saldo": None}
    por_nombre = {"RESERVA - MONTO": "reserva_monto", "SALDO - MONTO": "saldo_monto", "RAYA - SALDO": "raya_saldo"}
    for l in capas:
        nombre = l.get("name", "")
        if nombre.upper() in por_nombre:   # diseño «Tarjetas suaves»: el monto va en su propia capa
            loc[por_nombre[nombre.upper()]] = l["id"]
        elif l.get("kind") == "Type":
            t = ((l.get("text") or {}).get("text") or "").strip()
            tu = t.upper()
            if tu.startswith("FECHA"):
                loc["fecha"] = l["id"]
            elif re.match(r"^(BODA|XV)\s*\(", tu):
                loc["tema"] = l["id"]
            elif "|" in t:
                loc["nombre_lugar"] = l["id"]
            elif t.startswith("+"):
                loc["contacto"] = l["id"]
            elif tu.startswith("RESERVA"):
                loc["reserva"] = l["id"]
            elif tu.startswith("SALDO PENDIENTE"):
                loc["saldo"].append(l["id"])
        elif "ICONO DE BODA" in nombre.upper():
            loc["icono_boda"] = l["id"]
        elif "ICONO DE XV" in nombre.upper():
            loc["icono_xv"] = l["id"]
        elif (l.get("kind") == "Smart Object" and l.get("visible") and l.get("bounds")
              and not nombre.upper().startswith(("MARCO", "TARJETAS"))):
            x, y, w, h = l["bounds"]
            if x > 1400 and w > 400 and h > 800 and 1500 < y < 2000:   # marco con forma de celular
                loc["captura"] = l
    faltan = [k for k in ("fecha", "tema", "nombre_lugar", "contacto", "reserva", "captura")
              if not loc.get(k)]
    if faltan or not loc["saldo"]:
        raise RuntimeError("La plantilla no tiene las capas esperadas: " + ", ".join(faltan or ["saldo"]))
    return loc


# Borde derecho máximo (px) de los textos que pueden crecer: así no se salen de la hoja
# ni chocan con el dron.
LIMITE_DERECHO = {"tema": 2330, "nombre_lugar": 2330, "contacto": 1930,   # tema: hasta el borde de las
                  "fecha": 1175}                     # tarjetas; fecha y contacto: dentro de su ficha
# Centro (px) de la tarjeta de pago: ahí va «PAGO COMPLETADO» cuando ya no hay saldo (sin monto ni raya)
CENTRO_PAGO_X = 1185


_cache_fuentes = None


def olvidar_fuentes():
    """Se instalaron fuentes: volver a preguntarle a PhotoCraft (y reabrir el de la vista en vivo)."""
    global _cache_fuentes
    _cache_fuentes = None
    _sesion.reiniciar = True


def _fuentes_instaladas(cfg, sesion=None):
    global _cache_fuentes
    if sesion:   # el PhotoCraft de la vista en vivo ya está abierto: no hace falta otro
        return sesion.fuentes_instaladas()
    if _cache_fuentes is None:
        salida = _cli(cfg, "run", "--new", '{"width":8,"height":8}', "--cmd", "type.fonts")
        familias = set()
        for linea in salida.splitlines():
            if linea.startswith("{"):
                familias.update((json.loads(linea).get("result") or {}).get("families", []))
        _cache_fuentes = familias
    return _cache_fuentes


def _estilos_sustitutos(cfg, capas, ids, sesion=None):
    """Para cada capa editada cuya fuente no está instalada (p. ej. Myriad Pro), devuelve el
    estilo de la fuente sustituta calibrada para que mida y se vea igual que el original."""
    sustitutos = cfg.get("sustitutos_fuente") or {}
    instaladas = _fuentes_instaladas(cfg, sesion) if sustitutos else set()
    estilos = {}
    for l in capas:
        if l["id"] not in ids:
            continue
        t = l.get("text") or {}
        sus = sustitutos.get(t.get("font"))
        if sus and t.get("font") not in instaladas and t.get("sizePt"):
            estilos[l["id"]] = {"font": sus["fuente"], "fontStyle": sus.get("estilo", "Bold"),
                                "size": round(t["sizePt"] * sus.get("tamano", 1), 4),
                                "horizontalScale": sus.get("ancho", 100)}
    return estilos


def _argumentos(cmds):
    """[(comando, parámetros)] → argumentos --cmd/--params de «photocraft-cli run»."""
    args = []
    for nombre, params in cmds:
        args += ["--cmd", nombre, "--params", json.dumps(params, ensure_ascii=False)]
    return args


def _medir_cli(cfg, plantilla, cmds):
    """Aplica los comandos a la plantilla (sin guardar) y devuelve el resultado de cada uno."""
    return [json.loads(linea).get("result") or {}
            for linea in _cli(cfg, "run", plantilla, *_argumentos(cmds)).splitlines() if linea.startswith("{")]


def _ajustar_tamanos(cfg, plantilla, capas, loc, textos, estilos, medir=None, centros=None):
    """Mide los textos que cambian. Devuelve ({capa: estilo} para los que no caben,
    {capa: dx} para mantener la alineación del diseño: montos de la tarjeta de pago centrados donde
    están en la plantilla, etiquetas a la izquierda, o centradas en centros[capa] (px) si se indica).
    medir(cmds) → resultados; sin él se abre la plantilla con «photocraft-cli run»."""
    centros = centros or {}
    ids = {loc[k]: k for k in LIMITE_DERECHO}
    if loc["reserva_monto"]:   # etiquetas a la izquierda (tras su ícono) y montos centrados en su columna
        alinear = {c: "centro" for c in (loc["reserva_monto"], loc["saldo_monto"], *centros) if c in textos}
    else:
        alinear = {c: "centro" for c in (loc["reserva"], *loc["saldo"]) if c in textos}
    cmds = []
    for capa in [*ids, *alinear]:
        cmds.append(("type.edit", {"layer": capa, "text": textos[capa]}))
        if capa in estilos:
            cmds.append(("type.setStyle", {"layer": capa, **estilos[capa]}))
    tamano = {l["id"]: (l.get("text") or {}).get("sizePt") for l in capas}
    tamano.update({c: e["size"] for c, e in estilos.items()})
    original = {l["id"]: l.get("bounds") for l in capas}
    cajas = {}
    for res in (medir or (lambda c: _medir_cli(cfg, plantilla, c)))(cmds):
        if res.get("layer") in (*ids, *alinear) and res.get("bounds"):
            cajas[res["layer"]] = res["bounds"]  # la última medida (ya con la fuente final)
    movimientos = {}
    for capa, modo in alinear.items():
        if capa in cajas and original.get(capa):
            x0, _, x1, _ = cajas[capa]
            ox, _, ow, _ = original[capa]
            dx = (ox + ow) - x1 if modo == "derecha" else centros.get(capa, ox + ow / 2) - (x0 + x1) / 2
            if abs(dx) >= 2:
                movimientos[capa] = round(dx, 1)
    ajustes = {}
    for capa, (x0, _, x1, _) in cajas.items():
        if capa not in ids:
            continue
        limite = LIMITE_DERECHO[ids[capa]]
        if x1 <= limite or not tamano.get(capa):
            continue
        factor = (limite - x0) / (x1 - x0)
        texto = textos[capa]
        if ids[capa] == "nombre_lugar" and factor < 0.8 and " | " in texto:
            # Demasiado largo para una línea: nombre arriba y lugar abajo, sin achicar tanto.
            lineas = [p.strip() for p in texto.split(" | ", 1)]
            ancho_linea = (x1 - x0) * max(len(p) for p in lineas) / len(texto)
            factor = min(1.0, (limite - x0) / ancho_linea)
            textos[capa] = "\n".join(lineas)
            nuevo = round(tamano[capa] * min(factor * 0.97, 1), 4)
            ajustes[capa] = {"size": nuevo, "leading": round(nuevo * 1.15, 4)}
        elif factor < 1:
            ajustes[capa] = {"size": round(tamano[capa] * factor * 0.97, 4)}
    return ajustes, movimientos


def _recortar_bordes(im, tolerancia=18):
    """Quita los bordes lisos alrededor de la imagen (barras negras, márgenes blancos de una foto
    recortada): así la captura aprovecha todo el marco. Solo recorta si queda la mayor parte."""
    fondo = Image.new("RGB", im.size, im.getpixel((0, 0)))
    caja = ImageChops.difference(im, fondo).convert("L").point(lambda v: 255 if v > tolerancia else 0).getbbox()
    if caja and (caja[2] - caja[0]) * (caja[3] - caja[1]) >= 0.5 * im.width * im.height:
        return im.crop(caja)
    return im


def _preparar_captura(ruta, ancho_marco, alto_marco, destino):
    """Llena todo el marco con la captura, sin deformarla y sin bandas vacías:
    - si su forma se parece a la del marco (±15 %: las capturas de celular, el marco tiene su forma), la
      recorta apenas para cubrirlo (se pierden la barra de estado y la de abajo);
    - si no (p. ej. la captura alta de un celular), va completa al centro, a todo lo alto o ancho,
      sobre una copia ampliada, desenfocada y oscurecida de sí misma que cubre el resto del marco."""
    im = _recortar_bordes(ImageOps.exif_transpose(Image.open(ruta)).convert("RGB"))
    W, H = round(ancho_marco * 2), round(alto_marco * 2)     # el doble del marco: nítida al imprimir
    prop, prop_im = W / H, im.width / im.height
    if abs(prop_im / prop - 1) <= 0.15:
        ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.4)).save(destino)
        return
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
    fondo.save(destino)


def _nombre_archivo(carpeta, base):
    base = re.sub(r'[<>:"/\\|?*]+', "", base).strip() or "COMPROBANTE"
    ruta = carpeta / f"{base}.jpg"
    n = 2
    while ruta.exists():
        ruta = carpeta / f"{base} ({n}).jpg"
        n += 1
    return ruta


CONCEPTOS = {"RESERVA CON": "RESERVA", "ABONO": "ABONO", "PAGO FINAL": "PAGO FINAL"}

_ultima_captura = [None, None]   # [clave, archivo] de la captura ya preparada para la vista en vivo


def _captura_vista(ruta, ancho_marco, alto_marco):
    """Como _preparar_captura, pero la reutiliza mientras sea la misma imagen (la vista se repite
    en cada tecla). Devuelve (clave, archivo)."""
    st = os.stat(ruta)
    clave = (str(ruta), st.st_mtime, st.st_size, ancho_marco, alto_marco)
    if _ultima_captura[0] != clave:
        archivo = Path(tempfile.gettempdir()) / f"cinema_vista_captura_{os.getpid()}.png"
        _preparar_captura(ruta, ancho_marco, alto_marco, archivo)
        _ultima_captura[:] = [clave, archivo]
    return _ultima_captura[0], _ultima_captura[1]


def generar(datos, cfg=None, destino=None, calidad=None, sesion=None, lado=None):
    """datos: evento, paquete, festejado, lugar, fecha_evento (date), fecha_comprobante (date),
    contacto, total, monto (o reserva), captura (ruta de imagen).
    Opcionales: concepto ("RESERVA CON", "ABONO", "PAGO FINAL"), saldo (lo que falta después
    de este pago; si no se da, total - monto) y servicios ([[título, detalle, ícono], …]: el paquete
    con sus cambios y los extras; si no se da, los del paquete). Devuelve la ruta del JPG.
    sesion: SesionPhotoCraft ya abierta (vista en vivo); sin ella se usa «photocraft-cli run».
    lado: con sesión, la vista se pinta en memoria con ese lado mayor (px, hasta 2048) y se guarda
    como PNG junto a destino, en vez de exportar el JPG completo."""
    cfg = cfg or cargar_config()
    plantilla = ruta_plantilla(cfg)
    if not os.path.isfile(plantilla):
        raise RuntimeError(f"No se encontró la plantilla:\n{plantilla}")
    capas = _capas(cfg, plantilla)
    loc = _localizar(capas)

    evento = cfg["eventos"].get(datos["evento"], datos["evento"]).upper()
    fe: date = datos["fecha_evento"]
    fc: date = datos["fecha_comprobante"]
    monto = float(datos.get("monto", datos.get("reserva", 0)))
    concepto = datos.get("concepto", "RESERVA CON")
    saldo = float(datos["saldo"]) if "saldo" in datos else max(float(datos["total"]) - monto, 0)

    textos = {
        loc["fecha"]: f"FECHA: {fc.day}/{fc.month:02d}/{fc.year}",
        loc["tema"]: f"{evento} ({datos['paquete']}) - {fe.day} DE {MESES[fe.month - 1]}",
        loc["nombre_lugar"]: f"{datos['festejado'].strip()} | {datos['lugar'].strip()}",
        loc["contacto"]: datos["contacto"].strip(),
    }
    completo = saldo <= 0
    centros = {}
    if loc["reserva_monto"]:   # «RESERVA CON:  |  Q600»: etiqueta y monto en capas separadas
        textos[loc["reserva"]] = f"{concepto}:"
        textos[loc["reserva_monto"]] = quetzales(monto)
    else:
        textos[loc["reserva"]] = f"{concepto}: {quetzales(monto)}"
    for capa in loc["saldo"]:
        if completo:
            textos[capa] = "PAGO COMPLETADO"
            if loc["saldo_monto"]:    # sin monto ni raya: centrado en toda la fila
                centros[capa] = CENTRO_PAGO_X
        elif loc["saldo_monto"]:
            textos[capa] = "SALDO PENDIENTE:"
            textos[loc["saldo_monto"]] = quetzales(saldo)
        else:
            textos[capa] = f"SALDO PENDIENTE: {quetzales(saldo)}"

    if sesion:
        sesion.abrir(plantilla)
    estilos = _estilos_sustitutos(cfg, capas, textos, sesion)
    clave_lista, cmds_lista = _comandos_lista(cfg, plantilla, capas, servicios(cfg, datos),
                                              sesion.medir if sesion else (lambda c: _medir_cli(cfg, plantilla, c)))

    x, y, w, h = loc["captura"]["bounds"]
    tmp = clave_captura = None
    if datos.get("captura"):  # en la vista previa puede faltar: queda el recuadro de ejemplo
        if sesion:   # preparada una sola vez mientras sea la misma imagen
            clave_captura, tmp = _captura_vista(datos["captura"], w, h)
        else:
            tmp = Path(tempfile.gettempdir()) / f"cinema_captura_{os.getpid()}_{id(datos)}.png"
            _preparar_captura(datos["captura"], w, h, tmp)
    cmds_captura = []
    if tmp:
        cid = loc["captura"]["id"]
        cmds_captura = [("layer.smartObjects.replaceContents", {"layer": cid, "path": str(tmp)}),
                        ("edit.transform", {"layer": cid, "quad": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]})]
    if sesion:   # captura y lista quedan en la instantánea base: no se vuelven a poner en cada tecla
        sesion.poner_base((clave_captura, clave_lista), cmds_captura + cmds_lista)

    ajustes, movimientos = _ajustar_tamanos(cfg, plantilla, capas, loc, textos, estilos,
                                            sesion.medir_textos if sesion else None, centros)
    for capa, ajuste in ajustes.items():
        estilos.setdefault(capa, {}).update(ajuste)

    cmds = []

    def cmd(nombre, params):
        cmds.append((nombre, params))

    for capa, texto in textos.items():
        cmd("type.edit", {"layer": capa, "text": texto})
        if capa in estilos:
            cmd("type.setStyle", {"layer": capa, **estilos[capa]})
        if capa in movimientos:
            cmd("type.edit", {"layer": capa, "move": [movimientos[capa], 0]})
    vis_plantilla = {l["id"]: l.get("visible") for l in capas}

    def visible(capa, si):   # en la vista en vivo solo si cambia respecto a la plantilla
        if not (sesion and vis_plantilla.get(capa) == si):
            cmd("layer.setProps", {"layer": capa, "visible": si})
    es_xv = evento == "XV"
    if loc["icono_boda"]:
        visible(loc["icono_boda"], not es_xv)
    if loc["icono_xv"]:
        visible(loc["icono_xv"], es_xv)
    for clave in ("saldo_monto", "raya_saldo"):
        if loc[clave]:
            visible(loc[clave], not completo)

    if destino:  # vista previa: archivo temporal indicado, se sobrescribe
        destino = Path(destino)
        calidad = calidad or 80
    else:
        salida = Path(cfg["carpeta_salida"])
        salida.mkdir(parents=True, exist_ok=True)
        destino = _nombre_archivo(
            salida, f"COMPROBANTE - {evento} {datos['paquete']} - {datos['festejado'].strip()} - "
                    f"{fe.day:02d}-{fe.month:02d}-{fe.year} - {CONCEPTOS.get(concepto, concepto)}")
    calidad = calidad or cfg.get("calidad_jpg", 92)
    if sesion:
        sesion.aplicar_vista(cmds)
        if lado:   # vista en vivo: imagen en memoria del tamaño de la pantalla (sin exportar el JPG completo)
            destino = destino.with_suffix(".png")
            destino.write_bytes(sesion.pintar(lado))
        else:
            sesion.guardar(destino, calidad)
    else:
        try:
            # Sin metadatos: el XMP de los PSD puede traer textos viejos de las capas (datos de otros clientes)
            _cli(cfg, "run", plantilla, *_argumentos(cmds_lista + cmds_captura + cmds),
                 "--out", str(destino), "--quality", str(calidad), "--metadata", "none")
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)
    if not destino.exists():
        raise RuntimeError("PhotoCraft terminó pero no se creó el archivo.")
    return destino


# ================= Vista en vivo rápida =================
class SesionPhotoCraft:
    """PhotoCraft abierto en segundo plano («photocraft-cli serve») para la vista en vivo.
    - La plantilla se abre una sola vez (al abrir el programa, ver calentar_vista) y queda abierta con
      una instantánea «base» (con la captura del pago y la lista ya puestas) y otra «fija» con todo lo
      que no está cambiando (ver aplicar_vista): en cada tecla solo se tocan las capas que cambian y se
      pinta en memoria del tamaño de la pantalla. Los comandos van en lotes (un pedido cada uno).
    - Una plantilla por proceso: PhotoCraft numera las capas por proceso (una segunda plantilla, o la
      misma reabierta, ya no tiene los números que da «info»), así que si cambia el PSD se abre
      PhotoCraft de nuevo (≈1,5 s). Tener varias abiertas a la vez gastaría ~1 GB de RAM por plantilla.
    Una vista tarda ≈0,12 s, casi todo el «doc.render» de PhotoCraft (~0,11 s, igual a cualquier tamaño)."""
    ESPERA_MAX = 40   # s por pedido; si PhotoCraft se cuelga se cierra y se usa el método normal
    LADO_MAX = 2048   # lo más grande que pinta «doc.render»

    def __init__(self):
        self.proc = None
        self.clave = None        # (exe, carpetas de lectura, carpeta de escritura)
        self.doc = None          # {plantilla, clave, base0, base, captura} del documento abierto
        self.reiniciar = False   # se instalaron fuentes: hay que abrir PhotoCraft de nuevo
        self.n = 0
        self.candado = threading.Lock()
        atexit.register(self.cerrar)

    # ---- proceso ----
    def _iniciar(self, exe, lectura, escritura):
        clave = (exe, frozenset(lectura), escritura)
        if (self.proc and self.proc.poll() is None and self.clave[0] == exe and clave[1] <= self.clave[1]
                and self.clave[2] == escritura):
            return   # ya abierto, con los permisos necesarios
        self.cerrar()
        if not os.path.isfile(exe):
            raise RuntimeError("No se encontró PhotoCraft (photocraft-cli).\n"
                               "Instálalo o indica dónde está con el botón «PhotoCraft…».")
        args = [exe, "serve", "--automation-write-root", escritura]
        for carpeta in sorted(lectura):
            args += ["--automation-read-root", carpeta]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     errors="replace", creationflags=SIN_VENTANA)
        self.clave = clave

    def _pedir(self, metodo, params):
        proc = self.proc
        if not proc:
            raise RuntimeError("PhotoCraft (vista en vivo) no está abierto.")
        self.n += 1
        reloj = threading.Timer(self.ESPERA_MAX, self.cerrar)  # al cerrarse, readline() devuelve vacío
        reloj.start()
        try:
            proc.stdin.write(json.dumps({"id": self.n, "method": metodo, "params": params},
                                        ensure_ascii=False) + "\n")
            proc.stdin.flush()
            while True:
                linea = proc.stdout.readline()
                if not linea:
                    raise RuntimeError("PhotoCraft (vista en vivo) se cerró.")
                try:
                    r = json.loads(linea)
                except ValueError:
                    continue
                if r.get("id") == self.n:
                    break
        except (OSError, ValueError) as e:
            raise RuntimeError(f"PhotoCraft (vista en vivo) no responde: {e}")
        finally:
            reloj.cancel()
        if not r.get("ok"):
            raise RuntimeError(f"PhotoCraft (vista en vivo): {r.get('error')}")
        return r.get("result") or {}

    @staticmethod
    def _paso(comando, params):
        if comando == "layer.smartObjects.replaceContents":
            # en «serve» los comandos con rutas están desactivados: se usa el método del documento
            return "doc.replaceSmartObject", {**params, "path": str(Path(params["path"]).resolve())}
        return "engine.execute", {"command": comando, "params": params}

    def _ejecutar(self, comando, params):
        return self._pedir(*self._paso(comando, params))

    def _lote(self, cmds):
        """Varios comandos en un solo pedido («batch»). PhotoCraft se detiene en el primero que falla."""
        if not cmds:
            return []
        pasos = [dict(zip(("method", "params"), self._paso(c, p))) for c, p in cmds]
        r = self._pedir("batch", {"steps": pasos})
        resultados = r.get("results") or []
        for (comando, _), res in zip(cmds, resultados):
            if not res.get("ok"):
                raise RuntimeError(f"PhotoCraft (vista en vivo): {comando}: {res.get('error')}")
        if len(resultados) != len(cmds):
            raise RuntimeError("PhotoCraft (vista en vivo): el lote quedó incompleto.")
        return [res.get("result") or {} for res in resultados]

    def preparar(self, cfg):
        if self.reiniciar:
            self.reiniciar = False
            self.cerrar()
        tmp = str(Path(tempfile.gettempdir()).resolve())
        lectura = {tmp, str(Path(rutas.recurso("PLANTILLAS")).resolve())}
        self._iniciar(cfg.get("photocraft_cli") or "", lectura, tmp)

    def fuentes_instaladas(self):
        global _cache_fuentes
        if _cache_fuentes is None:   # se comparte con el método normal (mismas fuentes del sistema)
            _cache_fuentes = set(self._ejecutar("type.fonts", {}).get("families", []))
        return _cache_fuentes

    # ---- documento ----
    def abrir(self, plantilla):
        st = os.stat(plantilla)
        clave = (st.st_mtime, st.st_size)
        if self.doc and self.doc["plantilla"] == plantilla and self.doc["clave"] == clave:
            return
        exe, lectura, escritura = self.clave
        lectura = lectura | {str(Path(plantilla).parent.resolve())}
        if self.doc:   # otro paquete (o el PSD cambió): PhotoCraft nuevo para que las capas coincidan
            self.cerrar()
        self._iniciar(exe, lectura, escritura)
        self._pedir("doc.open", {"path": str(Path(plantilla).resolve())})
        base = self._ejecutar("history.newSnapshot", {"name": "base"})["snapshot"]
        self.doc = dict(plantilla=plantilla, clave=clave, base0=base, base=base, captura=None)
        self._olvidar_fija()

    def poner_base(self, clave, cmds):
        """Deja la captura del pago (o el recuadro de ejemplo) y la lista de servicios en la instantánea
        base del documento: solo se rehace cuando cambia alguna de las dos."""
        d = self.doc
        if d["captura"] == clave:
            return
        self._ejecutar("history.selectSnapshot", {"snapshot": d["base0"]})
        self._olvidar_fija()
        if d["base"] != d["base0"]:
            self._borrar_instantanea(d["base"])
            d["base"] = d["base0"]
        d["captura"] = None
        if cmds:
            self._lote(cmds)
            d["base"] = self._ejecutar("history.newSnapshot", {"name": "captura"})["snapshot"]
        d["captura"] = clave

    def _borrar_instantanea(self, n):
        try:
            self._ejecutar("history.deleteSnapshot", {"snapshot": n})
        except RuntimeError:
            pass

    def _volver(self, a="base"):
        return ("history.selectSnapshot", {"snapshot": self.doc[a]})

    def medir(self, cmds):
        """Vuelve a la base, aplica los comandos y devuelve el resultado de cada uno (todo en un pedido)."""
        self.doc["estado"] = None
        return self._lote([self._volver(), *cmds])[1:]

    # ---- vista en vivo incremental ----
    # Al escribir solo cambian una o dos capas. Se guarda una instantánea «fija» = base + todo lo de la
    # vista anterior menos las capas «calientes» (las que estaban cambiando), que ahí siguen como en la
    # plantilla. En cada tecla se vuelve a la fija y solo se ponen las calientes: menos comandos y menos
    # capas que PhotoCraft tiene que volver a dibujar. Las capas no se mezclan entre sí, así que el
    # resultado es idéntico a ponerlo todo desde la base. Las medidas (misma capa, texto y estilo →
    # misma caja) se recuerdan.
    MAX_MEDIDAS = 400

    def _olvidar_fija(self):
        d = self.doc
        if d.get("fija") is not None:
            self._borrar_instantanea(d["fija"])
        d.update(fija=None, horneado={}, calientes=set(), medidas={}, estado=None, puestas={}, ultimo={})

    @staticmethod
    def _por_capa(cmds):
        grupos = {}
        for c, p in cmds:
            grupos.setdefault(p["layer"], []).append((c, p))
        return grupos

    def medir_textos(self, cmds):
        """Como medir(), pero mide solo lo que no se ha medido antes, y si esas capas están calientes lo
        hace sobre la instantánea fija (queda puesto para aplicar_vista)."""
        d = self.doc
        grupos = self._por_capa(cmds)
        claves = {capa: json.dumps(g, sort_keys=True, ensure_ascii=False) for capa, g in grupos.items()}
        nuevas = [capa for capa in grupos if (capa, claves[capa]) not in d["medidas"]]
        d["estado"], d["puestas"] = None, {}
        if nuevas:
            if len(d["medidas"]) > self.MAX_MEDIDAS:
                d["medidas"].clear()
            desde = "fija" if d["fija"] is not None and set(nuevas) <= d["calientes"] else "base"
            pasos = [c for capa in nuevas for c in grupos[capa]]
            res = self._lote([self._volver(desde), *pasos])[1:]
            for capa in nuevas:
                n = len(grupos[capa])
                d["medidas"][(capa, claves[capa])], res = res[:n], res[n:]
            d["estado"], d["puestas"] = desde, {capa: grupos[capa] for capa in nuevas}
        return [r for capa in grupos for r in d["medidas"][(capa, claves[capa])]]

    def aplicar_vista(self, cmds):
        """Deja el documento con cmds (todos los cambios de la vista, contados desde la base)."""
        d = self.doc
        grupos = self._por_capa(cmds)
        ultimo = d["ultimo"]   # lo de la vista anterior
        cambiadas = {capa for capa in set(grupos) | set(ultimo) if grupos.get(capa, []) != ultimo.get(capa, [])}
        if d["fija"] is not None and cambiadas <= d["calientes"] and len(d["calientes"] - cambiadas) <= 1:
            sobre_fija = d["estado"] == "fija"
            puestas = d["puestas"] if sobre_fija else {}
            pasos = [] if sobre_fija else [self._volver("fija")]
            for capa in d["calientes"]:
                g, m = grupos.get(capa, []), puestas.get(capa)
                # lo medido ya está puesto: si la vista empieza igual, solo falta el resto (p. ej. moverla)
                pasos += g[len(m):] if m is not None and g[:len(m)] == m else g
            self._lote(pasos)
        else:   # cambió otra capa: se rehace la fija con todo menos las que cambian ahora
            calientes = cambiadas
            if d["fija"] is not None:
                self._borrar_instantanea(d["fija"])
                d["fija"] = None
            self._lote([self._volver(), *(c for capa, g in grupos.items() if capa not in calientes for c in g)])
            d["fija"] = self._ejecutar("history.newSnapshot", {"name": "fija"})["snapshot"]
            d["horneado"] = {capa: g for capa, g in grupos.items() if capa not in calientes}
            d["calientes"] = calientes
            self._lote([c for capa in calientes for c in grupos.get(capa, [])])
        d["estado"], d["puestas"], d["ultimo"] = None, {}, grupos

    def aplicar(self, cmds):
        self.doc["estado"] = None
        self._lote([self._volver(), *cmds])

    def pintar(self, lado):
        """La imagen del documento como PNG (bytes), con su lado mayor = lado px (máx. 2048)."""
        lado = int(max(256, min(lado, self.LADO_MAX)))
        return base64.b64decode(self._pedir("doc.render", {"maxSide": lado})["base64"])

    def guardar(self, destino, calidad):
        self._pedir("doc.save", {"path": str(Path(destino).resolve()), "quality": int(calidad),
                                 "metadata": "none"})

    def cerrar(self):
        proc, self.proc, self.doc = self.proc, None, None
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.kill()
            except OSError:
                pass


_sesion = SesionPhotoCraft()
_fallos_sesion = 0
_exe_sesion = None   # los fallos cuentan por PhotoCraft: si se elige otro, se vuelve a intentar


def calentar_vista(datos, cfg, lado):
    """Al abrir el programa (en segundo plano): abre PhotoCraft y la plantilla y prepara una vista sin
    mostrarla, para que la primera tecla no espere el arranque (~2 s). Si algo falla no avisa: la vista
    normal lo intentará y mostrará el error."""
    if not os.path.isfile(cfg.get("photocraft_cli") or "") or _fallos_sesion >= 2:
        return
    destino = Path(tempfile.gettempdir()) / f"cinema_vista_calentar_{os.getpid()}.jpg"
    try:
        with _sesion.candado:
            if _sesion.doc is not None:   # ya hubo una vista: nada que preparar
                return
            _sesion.preparar(cfg)
            ruta = generar(datos, cfg, destino, 80, sesion=_sesion, lado=lado)
        Path(ruta).unlink(missing_ok=True)
    except Exception:
        _sesion.cerrar()


def generar_vista(datos, cfg, destino, calidad=80, lado=None):
    """Vista previa en vivo: usa PhotoCraft ya abierto y pinta la imagen del tamaño de la pantalla
    (lado px). Si eso falla (o la versión de PhotoCraft no tiene «serve»), la hace con el método
    normal. Tras 2 fallos seguidos ya no lo intenta. Devuelve la ruta de la imagen."""
    global _fallos_sesion, _exe_sesion
    destino = Path(destino)
    exe = cfg.get("photocraft_cli") or ""
    if not os.path.isfile(exe):   # sin PhotoCraft: el método normal da el aviso de siempre
        return generar(datos, cfg, destino.with_suffix(".jpg"), calidad)
    if exe != _exe_sesion:
        _exe_sesion, _fallos_sesion = exe, 0
    if _fallos_sesion < 2:
        try:
            with _sesion.candado:
                _sesion.preparar(cfg)
                ruta = generar(datos, cfg, destino, calidad, sesion=_sesion, lado=lado or _sesion.LADO_MAX)
            _fallos_sesion = 0
            return ruta
        except Exception:
            _fallos_sesion += 1
            _sesion.cerrar()
    return generar(datos, cfg, destino.with_suffix(".jpg"), calidad)
