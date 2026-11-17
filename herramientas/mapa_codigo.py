"""Genera MAPA_CODIGO.md: cada archivo del programa con su número de líneas, para qué sirve y en qué línea
empieza cada clase y función. Sirve para ubicar código sin leer archivos completos (ahorra tokens).

    python herramientas/mapa_codigo.py              escribe PROGRAMA/MAPA_CODIGO.md
    python herramientas/mapa_codigo.py --revisar    no escribe; sale con 1 si el mapa está desactualizado

Lo corre solo el gancho de git (pre-commit) antes de cada commit.
"""
import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "MAPA_CODIGO.md"
EXTENSIONES = {".py", ".cs", ".swift", ".ps1", ".sh", ".command", ".bat", ".spec", ".yml", ".json", ".svg",
               ".applescript", ".txt"}
NO_ENTRAR = {".git", "__pycache__", "dist", "build", "dist-mac", "build-mac", "dist-portable", "build-portable",
             "DISEÑOS ORIGINALES", "COMPROBANTES GENERADOS", "fuentes", "PLANTILLAS", ".venv", "herramientas_tmp"}
NO_LISTAR = {"MAPA_CODIGO.md", "portable.flag"}


def _primera_frase(texto):
    texto = " ".join((texto or "").strip().split())
    m = re.match(r"(.+?[.:;])(\s|$)", texto)
    frase = m.group(1) if m else texto
    return frase[:150].rstrip(" .:;")


def _python(ruta, src):
    try:
        arbol = ast.parse(src)
    except SyntaxError:
        return "", []
    desc = _primera_frase(ast.get_docstring(arbol) or "")
    partes = []
    for n in arbol.body:
        if isinstance(n, ast.ClassDef):
            metodos = [f"{m.name}:{m.lineno}" for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            partes.append(f"**{n.name}**:{n.lineno}" + (f" ({', '.join(metodos)})" if metodos else ""))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            partes.append(f"{n.name}():{n.lineno}")
    return desc, partes


def _comentario_inicial(lineas, marcas):
    """Primera línea de comentario útil del encabezado (sin separadores ni shebang)."""
    for l in lineas[:25]:
        s = l.strip()
        for m in marcas:
            if s.startswith(m):
                s = s[len(m):].strip(" =-/*#")
                if s and not s.startswith("!") and "-*-" not in l and len(s) > 12:
                    return _primera_frase(s)
    return ""


def _regex(lineas, patrones):
    partes = []
    for i, l in enumerate(lineas, 1):
        for pat, fmt in patrones:
            m = re.match(pat, l)
            if m:
                partes.append(fmt.format(*m.groups(), n=i))
                break
    return partes


PATRONES = {
    ".cs": [(r"^\s*(?:public |internal |static |sealed )*class (\w+)", "**{0}**:{n}"),
            (r"^\s*(?:public |private |protected |internal |static |override |readonly )+[\w<>\[\], ]+? (\w+)\s*\([^;]*$",
             "{0}:{n}")],
    ".swift": [(r"^\s*(?:final |private |public )*(?:class|struct|extension|enum) (\w+)", "**{0}**:{n}"),
               (r"^\s*(?:@\w+ )?(?:private |public |static |override )*func (\w+)", "{0}:{n}")],
    ".ps1": [(r"^\s*function ([\w-]+)", "{0}():{n}"), (r"^\s*#\s*(\d\)\s.{3,60})", "{0}:{n}")],
    ".sh": [(r"^\s*(\w+)\(\)\s*\{", "{0}():{n}"), (r"^#\s*(\d\)\s.{3,60})", "{0}:{n}")],
    ".command": [(r"^echo \"(\[\d/\d\][^\"]{0,50})", "{0}:{n}")],
    ".bat": [(r"^echo (\[\d/\d\].{0,50})", "{0}:{n}"), (r"^:(\w+)", ":{0}:{n}")],
    ".yml": [(r"^\s*- name: (.{3,70})", "{0}:{n}")],
}
MARCAS = {".py": ["#"], ".cs": ["//"], ".swift": ["//"], ".ps1": ["#"], ".sh": ["#"], ".command": ["#"],
          ".bat": ["rem", "REM"], ".yml": ["#"], ".spec": ["#"], ".applescript": ["--"]}


def describir(ruta):
    src = ruta.read_text(encoding="utf-8", errors="replace")
    lineas = src.splitlines()
    ext = ruta.suffix.lower()
    if ext == ".py":
        desc, partes = _python(ruta, src)
        desc = desc or _comentario_inicial(lineas, ["#"])
    elif ext == ".json":
        try:
            import json
            claves = list(json.loads(src).keys())
        except Exception:
            claves = []
        desc, partes = "claves: " + ", ".join(claves[:14]), []
    elif ext == ".txt":
        desc, partes = _primera_frase(lineas[0] if lineas else ""), []
    elif ext == ".svg":
        m = re.search(r"<!--\s*(.*?)\s*-->", src)
        desc, partes = (m.group(1) if m else "imagen vectorial"), []
    else:
        desc = _comentario_inicial(lineas, MARCAS.get(ext, ["#"]))
        partes = _regex(lineas, PATRONES.get(ext, []))
    return len(lineas), desc, partes


def archivos():
    for r in sorted(RAIZ.rglob("*"), key=lambda p: (len(p.relative_to(RAIZ).parts), str(p).lower())):
        rel = r.relative_to(RAIZ)
        if any(p in NO_ENTRAR for p in rel.parts[:-1]) or not r.is_file() or r.name in NO_LISTAR:
            continue
        if r.suffix.lower() in EXTENSIONES or r.name in {".gitignore", ".gitattributes", "README.md"}:
            yield r


def generar():
    out = ["# Mapa del código — Comprobantes · Cinema Productions",
           "",
           "Generado por `herramientas/mapa_codigo.py` (se actualiza solo en cada commit). "
           "Formato: `archivo` (líneas) — para qué sirve · **Clase**:línea (método:línea, …) · función():línea.",
           "Abre solo el tramo que necesites: Read con offset/limit, o Grep. No leas archivos grandes completos.",
           ""]
    carpeta_actual = None
    for r in archivos():
        rel = r.relative_to(RAIZ)
        carpeta = str(rel.parent).replace("\\", "/") if rel.parent != Path(".") else "(raíz)"
        if carpeta != carpeta_actual:
            out += ["", f"## {carpeta}"]
            carpeta_actual = carpeta
        if r.suffix.lower() in {".gitignore", ".gitattributes"} or r.name.startswith(".git"):
            n = len(r.read_text(encoding="utf-8", errors="replace").splitlines())
            out.append(f"- `{r.name}` ({n})")
            continue
        n, desc, partes = describir(r)
        linea = f"- `{r.name}` ({n})" + (f" — {desc}" if desc else "")
        if partes:
            linea += " · " + " · ".join(partes)
        out.append(linea)
    binarios = {
        "PLANTILLAS": "la plantilla única COMPROBANTE.psd (la lista de servicios la dibuja lista.py en cada comprobante), sus medidas COMPROBANTE.json y la VISTA PREVIA.jpg; se rehacen con crear_plantillas.py",
        "recursos": "icono.svg/.png/.ico/.icns y fuentes/ del diseño (van en los instaladores)",
        "DISEÑOS ORIGINALES": "PSD originales y COTIZACIONES del estudio (fuera de git; NO leer)",
        "COMPROBANTES GENERADOS": "JPG generados (fuera de git; NO leer)",
    }
    out += ["", "## Carpetas sin código (no abrir)"] + [f"- `{k}/` — {v}" for k, v in binarios.items()]
    return "\n".join(out).replace("\n\n\n", "\n\n").strip() + "\n"


if __name__ == "__main__":
    texto = generar()
    actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
    if "--revisar" in sys.argv:
        sys.exit(0 if actual == texto else 1)
    if actual != texto:
        SALIDA.write_text(texto, encoding="utf-8", newline="\n")
    if "--silencioso" not in sys.argv:
        print(f"MAPA_CODIGO.md: {len(texto.splitlines())} líneas, {len(texto)} caracteres")
