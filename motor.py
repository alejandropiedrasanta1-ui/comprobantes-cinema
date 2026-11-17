"""Motor del generador: abre la plantilla PSD con PhotoCraft (sin ventana),
cambia los textos, coloca la captura del pago y exporta un JPG.
Las plantillas originales nunca se modifican."""
import atexit
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

from PIL import Image, ImageOps

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


def ruta_plantilla(paquete):
    return str(rutas.recurso(paquete["plantilla"]))


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
    loc = {"saldo": [], "icono_boda": None, "icono_xv": None, "captura": None}
    for l in capas:
        nombre = l.get("name", "")
        if l.get("kind") == "Type":
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
        elif l.get("kind") == "Smart Object" and l.get("visible") and l.get("bounds"):
            x, y, w, h = l["bounds"]
            if x > 1400 and w > 500 and h > 800 and 1500 < y < 2000:
                loc["captura"] = l
    faltan = [k for k in ("fecha", "tema", "nombre_lugar", "contacto", "reserva", "captura")
              if not loc.get(k)]
    if faltan or not loc["saldo"]:
        raise RuntimeError("La plantilla no tiene las capas esperadas: " + ", ".join(faltan or ["saldo"]))
    return loc


# Borde derecho máximo (px) de los textos que pueden crecer: así no se salen de la hoja
# ni chocan con el dron.
LIMITE_DERECHO = {"tema": 2340, "nombre_lugar": 2340, "contacto": 1950}


_cache_fuentes = None


def _fuentes_instaladas(cfg):
    global _cache_fuentes
    if _cache_fuentes is None:
        salida = _cli(cfg, "run", "--new", '{"width":8,"height":8}', "--cmd", "type.fonts")
        familias = set()
        for linea in salida.splitlines():
            if linea.startswith("{"):
                familias.update((json.loads(linea).get("result") or {}).get("families", []))
        _cache_fuentes = familias
    return _cache_fuentes


def _estilos_sustitutos(cfg, capas, ids):
    """Para cada capa editada cuya fuente no está instalada (p. ej. Myriad Pro), devuelve el
    estilo de la fuente sustituta calibrada para que mida y se vea igual que el original."""
    sustitutos = cfg.get("sustitutos_fuente") or {}
    instaladas = _fuentes_instaladas(cfg) if sustitutos else set()
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


def _ajustar_tamanos(cfg, plantilla, capas, loc, textos, estilos, medir=None):
    """Mide los textos que cambian. Devuelve ({capa: estilo} para los que no caben,
    {capa: dx} para mantener la alineación del diseño: reserva a la derecha, saldo centrado).
    medir(cmds) → resultados; sin él se abre la plantilla con «photocraft-cli run»."""
    ids = {loc[k]: k for k in LIMITE_DERECHO}
    alinear = {loc["reserva"]: "derecha", **{s: "centro" for s in loc["saldo"]}}
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
            dx = (ox + ow) - x1 if modo == "derecha" else (ox + ow / 2) - (x0 + x1) / 2
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


def _preparar_captura(ruta, ancho_marco, alto_marco, destino):
    """Encaja la captura en la proporción del marco con fondo blanco (sin deformarla)."""
    im = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    im.thumbnail((1600, 2400))
    prop = ancho_marco / alto_marco
    if im.width / im.height < prop:
        W, H = round(im.height * prop), im.height
    else:
        W, H = im.width, round(im.width / prop)
    lienzo = Image.new("RGB", (W, H), "white")
    lienzo.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    lienzo.save(destino)


def _nombre_archivo(carpeta, base):
    base = re.sub(r'[<>:"/\\|?*]+', "", base).strip() or "COMPROBANTE"
    ruta = carpeta / f"{base}.jpg"
    n = 2
    while ruta.exists():
        ruta = carpeta / f"{base} ({n}).jpg"
        n += 1
    return ruta


CONCEPTOS = {"RESERVA CON": "RESERVA", "ABONO": "ABONO", "PAGO FINAL": "PAGO FINAL"}


def generar(datos, cfg=None, destino=None, calidad=None, sesion=None):
    """datos: evento, paquete, festejado, lugar, fecha_evento (date), fecha_comprobante (date),
    contacto, total, monto (o reserva), captura (ruta de imagen).
    Opcionales: concepto ("RESERVA CON", "ABONO", "PAGO FINAL") y saldo (lo que falta después
    de este pago; si no se da, total - monto). Devuelve la ruta del JPG.
    sesion: SesionPhotoCraft ya abierta (vista en vivo); sin ella se usa «photocraft-cli run»."""
    cfg = cfg or cargar_config()
    paquete = cfg["paquetes"][datos["paquete"]]
    plantilla = ruta_plantilla(paquete)
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
        loc["tema"]: f"{evento}({datos['paquete']}) - {fe.day} DE {MESES[fe.month - 1]}",
        loc["nombre_lugar"]: f"{datos['festejado'].strip()} | {datos['lugar'].strip()}",
        loc["contacto"]: datos["contacto"].strip(),
        loc["reserva"]: f"{concepto}: {quetzales(monto)}",
    }
    for capa in loc["saldo"]:
        textos[capa] = "PAGO COMPLETADO" if saldo <= 0 else f"SALDO PENDIENTE: {quetzales(saldo)}"

    estilos = _estilos_sustitutos(cfg, capas, textos)
    if sesion:
        sesion.abrir(plantilla)
    ajustes, movimientos = _ajustar_tamanos(cfg, plantilla, capas, loc, textos, estilos,
                                            sesion.medir if sesion else None)
    for capa, ajuste in ajustes.items():
        estilos.setdefault(capa, {}).update(ajuste)

    x, y, w, h = loc["captura"]["bounds"]
    tmp = None
    if datos.get("captura"):  # en la vista previa puede faltar: queda el recuadro de ejemplo
        tmp = Path(tempfile.gettempdir()) / f"cinema_captura_{os.getpid()}_{id(datos)}.png"
        _preparar_captura(datos["captura"], w, h, tmp)

    cmds = []

    def cmd(nombre, params):
        cmds.append((nombre, params))

    for capa, texto in textos.items():
        cmd("type.edit", {"layer": capa, "text": texto})
        if capa in estilos:
            cmd("type.setStyle", {"layer": capa, **estilos[capa]})
        if capa in movimientos:
            cmd("type.edit", {"layer": capa, "move": [movimientos[capa], 0]})
    es_xv = evento == "XV"
    if loc["icono_boda"]:
        cmd("layer.setProps", {"layer": loc["icono_boda"], "visible": not es_xv})
    if loc["icono_xv"]:
        cmd("layer.setProps", {"layer": loc["icono_xv"], "visible": es_xv})
    if tmp:
        cid = loc["captura"]["id"]
        cmd("layer.smartObjects.replaceContents", {"layer": cid, "path": str(tmp)})
        cmd("edit.transform", {"layer": cid, "quad": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]})

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
    try:
        if sesion:
            sesion.aplicar(cmds)
            sesion.guardar(destino, calidad)
        else:
            # Sin metadatos: el XMP de los PSD puede traer textos viejos de las capas (datos de otros clientes)
            _cli(cfg, "run", plantilla, *_argumentos(cmds),
                 "--out", str(destino), "--quality", str(calidad), "--metadata", "none")
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    if not destino.exists():
        raise RuntimeError("PhotoCraft terminó pero no se creó el archivo.")
    return destino


# ================= Vista en vivo rápida =================
class SesionPhotoCraft:
    """PhotoCraft abierto en segundo plano («photocraft-cli serve») para la vista en vivo: la plantilla
    se abre una sola vez y cada cambio solo edita los textos y exporta (≈0,4 s en vez de 2-3 s).
    Antes de cada vista se vuelve a la instantánea «base» (la plantilla tal como se abrió)."""
    ESPERA_MAX = 40  # s por pedido; si PhotoCraft se cuelga se cierra y se usa el método normal

    def __init__(self):
        self.proc = None
        self.clave = None        # (exe, carpetas de lectura, carpeta de escritura)
        self.plantilla = None    # (ruta, fecha de modificación) del documento abierto
        self.base = None         # id de la instantánea «base»
        self.n = 0
        atexit.register(self.cerrar)

    def _iniciar(self, exe, lectura, escritura):
        clave = (exe, frozenset(lectura), escritura)
        if self.proc and self.proc.poll() is None and self.clave == clave:
            return
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
        self.n += 1
        reloj = threading.Timer(self.ESPERA_MAX, self.cerrar)  # al cerrarse, readline() devuelve vacío
        reloj.start()
        try:
            self.proc.stdin.write(json.dumps({"id": self.n, "method": metodo, "params": params},
                                             ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            while True:
                linea = self.proc.stdout.readline()
                if not linea:
                    raise RuntimeError("PhotoCraft (vista en vivo) se cerró.")
                try:
                    r = json.loads(linea)
                except ValueError:
                    continue
                if r.get("id") == self.n:
                    break
        except (OSError, ValueError, AttributeError) as e:
            raise RuntimeError(f"PhotoCraft (vista en vivo) no responde: {e}")
        finally:
            reloj.cancel()
        if not r.get("ok"):
            raise RuntimeError(f"PhotoCraft (vista en vivo): {r.get('error')}")
        return r.get("result") or {}

    def _ejecutar(self, comando, params):
        return self._pedir("engine.execute", {"command": comando, "params": params})

    def preparar(self, cfg, destino):
        tmp = str(Path(tempfile.gettempdir()).resolve())
        lectura = {tmp, str(Path(rutas.recurso("PLANTILLAS")).resolve())}
        self._iniciar(cfg.get("photocraft_cli") or "", lectura, str(Path(destino).parent.resolve()))

    def abrir(self, plantilla):
        clave = (plantilla, os.path.getmtime(plantilla))
        if self.plantilla == clave:
            return
        carpeta = str(Path(plantilla).parent.resolve())
        if carpeta not in self.clave[1]:  # plantilla fuera de PLANTILLAS: hay que reiniciar con permiso
            self._iniciar(self.clave[0], self.clave[1] | {carpeta}, self.clave[2])
        if self.plantilla:
            try:
                self._pedir("doc.close", {})
            except RuntimeError:
                pass
        self.plantilla = None
        self._pedir("doc.open", {"path": str(Path(plantilla).resolve())})
        self.base = self._ejecutar("history.newSnapshot", {"name": "base"})["snapshot"]
        self.plantilla = clave

    def _a_base(self):
        self._ejecutar("history.selectSnapshot", {"snapshot": self.base})

    def medir(self, cmds):
        self._a_base()
        return [self._ejecutar(n, p) for n, p in cmds]

    def aplicar(self, cmds):
        self._a_base()
        for nombre, params in cmds:
            if nombre == "layer.smartObjects.replaceContents":
                # en «serve» los comandos con rutas están desactivados: se usa el método del documento
                self._pedir("doc.replaceSmartObject", {**params, "path": str(Path(params["path"]).resolve())})
            else:
                self._ejecutar(nombre, params)

    def guardar(self, destino, calidad):
        self._pedir("doc.save", {"path": str(Path(destino).resolve()), "quality": int(calidad),
                                 "metadata": "none"})

    def cerrar(self):
        proc, self.proc, self.plantilla = self.proc, None, None
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


def generar_vista(datos, cfg, destino, calidad=80):
    """Vista previa en vivo: usa PhotoCraft ya abierto; si eso falla (o la versión de PhotoCraft no
    tiene «serve»), hace la vista con el método normal. Tras 2 fallos seguidos ya no lo intenta."""
    global _fallos_sesion
    if _fallos_sesion < 2:
        try:
            _sesion.preparar(cfg, destino)
            ruta = generar(datos, cfg, destino, calidad, sesion=_sesion)
            _fallos_sesion = 0
            return ruta
        except Exception:
            _fallos_sesion += 1
            _sesion.cerrar()
            if not os.path.isfile(cfg.get("photocraft_cli") or ""):
                raise
    return generar(datos, cfg, destino, calidad)
