#!/usr/bin/env python3
"""PhotoCraft simulado, solo para pruebas donde no hay PhotoCraft (la Mac de GitHub Actions).

Responde lo mismo que «photocraft-cli» en lo que usa el programa:
  info --compact <psd>                       capas (de photocraft_simulado_capas.json)
  run <psd|--new J> --cmd C --params P … [--out F --quality Q --metadata none]
  serve                                      líneas JSON por stdin/stdout (vista en vivo)
La «imagen» es la VISTA PREVIA de la plantilla con los textos nuevos dibujados encima y la marca
«PhotoCraft simulado»: sirve para probar el flujo y los tiempos del programa, no el diseño."""
import base64
import copy
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
CAPAS = json.loads((AQUI / "photocraft_simulado_capas.json").read_text(encoding="utf-8"))
ANCHO, ALTO = CAPAS["width"], CAPAS["height"]
PX_POR_PT = 4.1667
PAUSA = 0.05   # s: un poco de trabajo, como el real


def _planas(capas):
    for l in capas:
        yield l
        yield from _planas(l.get("children") or [])


ORIGINAL = {l["id"]: l for l in _planas(CAPAS["layers"])}
FUENTES = sorted({(l.get("text") or {}).get("font") for l in ORIGINAL.values()} - {None})
CAPTURA = next((l["id"] for l in ORIGINAL.values() if l.get("kind") == "Smart Object" and l.get("bounds")
                and l["bounds"][0] > 1400 and l["bounds"][2] > 400 and l["bounds"][3] > 800), None)


class Documento:
    def __init__(self, psd):
        psd = Path(psd)
        if not psd.is_file():
            raise FileNotFoundError(f"no existe {psd}")
        self.fondo = psd.with_name("VISTA PREVIA.jpg")     # la vista previa de la plantilla única
        self.estado = {"textos": {}, "dx": {}, "tam": {}, "captura": None}
        self.instantaneas = {}

    # ---- comandos del motor ----
    def caja(self, capa):
        o = ORIGINAL[capa]
        x, y, w, h = o["bounds"]
        texto = self.estado["textos"].get(capa, (o.get("text") or {}).get("text", ""))
        pt = self.estado["tam"].get(capa, (o.get("text") or {}).get("sizePt", 12))
        largo = max(len(linea) for linea in texto.split("\n")) if texto else 0
        x0 = x + self.estado["dx"].get(capa, 0)
        return [round(x0), y, round(x0 + largo * pt * PX_POR_PT * 0.55), y + h]

    def lineas(self, capa, texto, runs):
        """Renglones de una capa de texto con estilos por tramo: cada uno baja lo que diga su interlineado."""
        x, y, _, _ = ORIGINAL[capa]["bounds"]
        lineas, inicio, base = [], 0, 0.0
        for renglon in texto.split("\n"):
            leading = next((r.get("leading", 12) for r in runs if r["start"] <= inicio < r["end"]), 12)
            base += leading * PX_POR_PT
            lineas.append({"start": inicio, "baseline": base})
            inicio += len(renglon) + 1
        return {"transform": [1, 0, 0, 1, x, y], "lines": lineas}

    def ejecutar(self, comando, p):
        capa = p.get("layer")
        if comando == "type.edit":
            if capa not in ORIGINAL:
                return {}
            if "text" in p:
                self.estado["textos"][capa] = p["text"]
            if "move" in p:
                self.estado["dx"][capa] = self.estado["dx"].get(capa, 0) + p["move"][0]
            r = {"layer": capa, "bounds": self.caja(capa)}
            if p.get("runs"):     # la lista del comprobante: líneas con su renglón base, como el real
                r.update(self.lineas(capa, p["text"], p["runs"]))
            return r
        if comando == "type.setStyle":
            if "size" in p:
                self.estado["tam"][capa] = p["size"]
            return {"layer": capa, "bounds": self.caja(capa)}
        if comando == "type.fonts":
            return {"families": FUENTES}
        if comando == "layer.smartObjects.replaceContents":
            if capa == CAPTURA:     # la de la lista (rayas) no se dibuja en la simulación
                self.estado["captura"] = p["path"]
            return {"layer": capa}
        if comando == "history.newSnapshot":
            n = max(self.instantaneas, default=0) + 1
            self.instantaneas[n] = copy.deepcopy(self.estado)
            return {"name": p.get("name"), "snapshot": n}
        if comando == "history.selectSnapshot":
            self.estado = copy.deepcopy(self.instantaneas[p["snapshot"]])
            return {"snapshot": p["snapshot"]}
        if comando == "history.deleteSnapshot":
            self.instantaneas.pop(p["snapshot"], None)
            return {"snapshot": p["snapshot"], "snapshots": len(self.instantaneas)}
        return {}

    # ---- imagen ----
    def pintar(self, lado=None):
        time.sleep(PAUSA)
        im = Image.open(self.fondo).convert("RGB") if self.fondo.is_file() else Image.new("RGB", (ANCHO, ALTO), "white")
        im = im.resize((ANCHO, ALTO)) if im.size != (ANCHO, ALTO) else im
        d = ImageDraw.Draw(im)
        for capa, texto in self.estado["textos"].items():
            x, y, w, h = ORIGINAL[capa]["bounds"]
            d.rectangle([x - 6, y - 6, max(x + w, self.caja(capa)[2]) + 6, y + h + 6], fill="white")
            pt = self.estado["tam"].get(capa, ORIGINAL[capa]["text"].get("sizePt", 12))
            letra = ImageFont.load_default(size=max(10, int(pt * PX_POR_PT * 0.8)))
            d.multiline_text((self.caja(capa)[0], y), texto, fill="black", font=letra)
        if self.estado["captura"]:
            cap = next(l for l in ORIGINAL.values() if l.get("kind") == "Smart Object" and l["bounds"][0] > 1400
                       and l["bounds"][2] > 400)
            x, y, w, h = cap["bounds"]
            im.paste(Image.open(self.estado["captura"]).convert("RGB").resize((w, h)), (x, y))
        d.text((40, ALTO - 120), "PhotoCraft simulado (prueba)", fill=(220, 0, 0),
               font=ImageFont.load_default(size=70))
        if lado:
            im.thumbnail((lado, lado))
        return im


def _serve():
    doc = None
    for linea in sys.stdin:
        if not linea.strip():
            continue
        pedido = json.loads(linea)
        metodo, p = pedido.get("method"), pedido.get("params") or {}
        try:
            if metodo == "doc.open":
                doc = Documento(p["path"])
                r = {"index": 0, "width": ANCHO, "height": ALTO, "layers": len(ORIGINAL), "name": Path(p["path"]).name}
            elif metodo == "engine.execute":
                if p["command"] == "type.fonts":
                    r = {"families": FUENTES}
                elif not doc:
                    raise RuntimeError("no document open")
                else:
                    r = doc.ejecutar(p["command"], p.get("params") or {})
            elif metodo == "doc.replaceSmartObject":
                if not Path(p["path"]).is_file():
                    raise RuntimeError(f"automation read `{p['path']}` failed (NotFound)")
                r = doc.ejecutar("layer.smartObjects.replaceContents", p)
            elif metodo == "doc.render":
                if p.get("maxSide", 1024) > 2048:
                    raise RuntimeError("automation preview side exceeds 2048 pixels")
                b = io.BytesIO()
                doc.pintar(p.get("maxSide", 1024)).save(b, "PNG")
                r = {"base64": base64.b64encode(b.getvalue()).decode(), "mime": "image/png"}
            elif metodo == "doc.save":
                doc.pintar().save(p["path"], quality=p.get("quality", 92))
                r = {"path": p["path"]}
            elif metodo in ("doc.close", "doc.select", "session.list", "methods"):
                r = {}
            else:
                raise RuntimeError(f"método desconocido {metodo}")
            respuesta = {"id": pedido.get("id"), "ok": True, "result": r}
        except Exception as e:
            respuesta = {"id": pedido.get("id"), "ok": False, "error": str(e)}
        sys.stdout.write(json.dumps(respuesta, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _run(args):
    doc, salida, calidad, i = None, None, 92, 0
    while i < len(args):
        a = args[i]
        if a == "--new":
            i += 2
            continue
        if a == "--cmd":
            con_params = i + 3 < len(args) and args[i + 2] == "--params"   # «type.fonts» va sin parámetros
            comando, params = args[i + 1], json.loads(args[i + 3]) if con_params else {}
            r = doc.ejecutar(comando, params) if doc else ({"families": FUENTES} if comando == "type.fonts" else {})
            print(json.dumps({"command": comando, "result": r}, ensure_ascii=False))
            i += 4 if con_params else 2
            continue
        if a == "--out":
            salida = args[i + 1]
        elif a == "--quality":
            calidad = int(args[i + 1])
        elif not a.startswith("--") and doc is None and a.lower().endswith((".psd", ".psb")):
            doc = Documento(a)
        i += 2 if a in ("--out", "--quality", "--metadata") else 1
    if salida and doc:
        time.sleep(1)   # el real tarda 1-3 s en abrir el PSD
        doc.pintar().save(salida, quality=calidad)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("--version", "-V"):
        print("photocraft-cli simulado")
    elif args[0] == "serve":
        _serve()
    elif args[0] == "info":
        print(json.dumps(CAPAS, ensure_ascii=False))
    elif args[0] == "run":
        _run(args[1:])
    else:
        print(f"comando no simulado: {args[0]}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
