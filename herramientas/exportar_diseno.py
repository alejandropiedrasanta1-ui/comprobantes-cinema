"""Exporta el diseño de PLANTILLAS/COMPROBANTE.psd para dibujar los comprobantes sin PhotoCraft.

Solo hace falta (y solo funciona) en una computadora con PhotoCraft, y solo cuando cambia el PSD
(después de crear_plantillas.py). Deja en PLANTILLAS/DISENO/:
  fondo.jpg        la hoja con todo lo fijo (sin los textos, íconos ni rayas que cambian)
  <capa>.png       cada ícono, el reloj de arena con su raya y los íconos de Boda y XV (con transparencia,
                   recortados a su caja)
  diseno.json      posición, letra, tamaño y escala de cada texto que cambia, y la caja de cada ícono
Uso:  python herramientas/exportar_diseno.py"""
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))
import lista   # noqa: E402
import photocraft as motor   # noqa: E402  (PhotoCraft: solo aquí, en desarrollo)

DESTINO = AQUI / "PLANTILLAS" / "DISENO"


def _hojas(capas):
    return [l for l in capas if l.get("kind") != "Group"]


def _texto(info):
    """Lo que se necesita para dibujar un texto: transformación, letra, tamaño, color, interlineado."""
    st = info["runs"][0]["style"]
    c = st["color"]["c"]
    return {"transform": info["transform"], "fuente": st["postscript_name"], "familia": st["font_family"],
            "pt": st["size_pt"], "color": "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3]),
            "interlineado_pt": st["leading_pt"], "escala_h": st["horizontal_scale"],
            "tracking": st["tracking"], "alineacion": info["paragraphs"][0]["style"]["align"],
            "texto": info["text"], "caja": info["bounds"]}


def exportar():
    cfg = motor.cargar_config()
    plantilla = motor.ruta_plantilla(cfg)
    capas = motor._capas(cfg, plantilla)
    loc = motor._localizar(capas)
    por_nombre = {l["name"]: l for l in capas}
    iconos = {n[len(lista.PREFIJO_ICONO):]: l for n, l in por_nombre.items() if n.startswith(lista.PREFIJO_ICONO)}
    id_lista = por_nombre[lista.CAPA_LISTA]["id"]
    id_rayas = por_nombre[lista.CAPA_RAYAS]["id"]
    textos = {k: loc[k] for k in ("fecha", "tema", "nombre_lugar", "contacto", "reserva",
                                  "reserva_monto", "saldo_monto")}
    textos["saldo"] = loc["saldo"][0]
    variables = {*textos.values(), *loc["saldo"], id_lista, id_rayas, loc["raya_saldo"], loc["icono_boda"],
                 loc["icono_xv"], *(l["id"] for l in iconos.values())}
    sueltas = {"raya_saldo": loc["raya_saldo"], "boda": loc["icono_boda"], "xv": loc["icono_xv"],
               **{f"icono_{k}": l["id"] for k, l in iconos.items()}}

    DESTINO.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir())
    s = motor._sesion
    s.preparar(cfg)
    s.abrir(plantilla)
    disenio = {"hoja": list(lista.HOJA), "textos": {}, "lista": _texto(s._ejecutar("type.info", {"layer": id_lista})),
               "piezas": {}, "captura": loc["captura"]["bounds"],
               "iconos": motor._meta_plantilla(plantilla)["iconos"]}   # tamaño de cada ícono en la lista
    for clave, capa in textos.items():
        disenio["textos"][clave] = _texto(s._ejecutar("type.info", {"layer": capa}))

    visibles = {l["id"]: bool(l.get("visible")) for l in capas}

    def guardar(ruta):
        s._pedir("doc.save", {"path": str(Path(ruta).resolve()), "quality": 100, "metadata": "none"})

    # 1) El fondo: todo lo fijo tal como está en la plantilla
    s._lote([("layer.setProps", {"layer": c, "visible": False}) for c in variables if visibles.get(c)])
    png = tmp / "cinema_fondo.png"
    guardar(png)
    with Image.open(png) as im:
        im.convert("RGB").save(DESTINO / "fondo.jpg", quality=95, subsampling=0)
    png.unlink(missing_ok=True)

    # 2) Cada pieza sola, con transparencia
    s._lote([("layer.setProps", {"layer": l["id"], "visible": False}) for l in _hojas(capas)])
    for nombre, capa in sueltas.items():
        s._ejecutar("layer.setProps", {"layer": capa, "visible": True})
        png = tmp / f"cinema_pieza_{nombre}.png"
        guardar(png)
        s._ejecutar("layer.setProps", {"layer": capa, "visible": False})
        with Image.open(png) as im:
            im = im.convert("RGBA")
            caja = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()   # sin el punto casi invisible
            if caja:
                im.crop(caja).save(DESTINO / f"{nombre}.png", optimize=True)
                disenio["piezas"][nombre] = list(caja)
        png.unlink(missing_ok=True)
    s.cerrar()
    (DESTINO / "diseno.json").write_text(json.dumps(disenio, ensure_ascii=False, indent=1), encoding="utf-8")
    return DESTINO


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(exportar())
