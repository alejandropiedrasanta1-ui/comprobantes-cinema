"""Dibuja el fondo de la ventana del .dmg de Mac («Doble clic para instalar»), como el de CineSlide.

Genera fondo.png (660x400) y fondo@2x.png (1320x800) junto a este archivo. Se ejecuta en Windows (usa Segoe UI)
y las imágenes se guardan en el repositorio; la Mac solo las une en fondo.tiff con tiffutil.
El ícono «Instalar Comprobantes» queda centrado en (330, 200): dmg_ajustes.py lo pone en (330, 176), que en
Finder es el centro del ícono más su nombre.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

AQUI = Path(__file__).resolve().parent
K = 2                                   # se dibuja al doble y se reduce para la versión normal
W, H = 660 * K, 400 * K
CX, CY, R = 330 * K, 200 * K, 80 * K    # centro del ícono y radio del anillo
FUENTES = Path("C:/Windows/Fonts")


def fuente(nombre, tam):
    return ImageFont.truetype(str(FUENTES / nombre), int(tam * K))


def centrado(d, y, texto, f, color, espaciado=0.0):
    if not espaciado:
        w = d.textlength(texto, font=f)
        d.text(((W - w) / 2, y), texto, font=f, fill=color)
        return
    anchos = [d.textlength(c, font=f) for c in texto]
    total = sum(anchos) + espaciado * K * (len(texto) - 1)
    x = (W - total) / 2
    for c, a in zip(texto, anchos):
        d.text((x, y), c, font=f, fill=color)
        x += a + espaciado * K


def linea_mixta(d, y, partes):
    """Una línea centrada con trozos de distinta fuente/color: [(texto, fuente, color), ...]."""
    total = sum(d.textlength(t, font=f) for t, f, _ in partes)
    x = (W - total) / 2
    for t, f, c in partes:
        d.text((x, y), t, font=f, fill=c)
        x += d.textlength(t, font=f)


def fondo():
    im = Image.new("RGB", (W, H))
    px = im.load()
    a, b = (58, 12, 17), (12, 9, 10)                     # rojo vino arriba a la izquierda → casi negro
    for y in range(H):
        for x in range(W):
            t = min(1.0, (x / W) * 0.45 + (y / H) * 0.75)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    im = im.convert("RGBA")

    # resplandor detrás del ícono y una luz cálida en la esquina
    luz = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dl = ImageDraw.Draw(luz)
    dl.ellipse((CX - 150 * K, CY - 150 * K, CX + 150 * K, CY + 150 * K), fill=(224, 38, 43, 70))
    dl.ellipse((W - 170 * K, H - 150 * K, W + 90 * K, H + 110 * K), fill=(255, 154, 61, 34))
    im.alpha_composite(luz.filter(ImageFilter.GaussianBlur(60 * K)))

    # partículas (siempre las mismas)
    rnd = random.Random(7)
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    for _ in range(46):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        if math.hypot(x - CX, y - CY) < (R + 20 * K):
            continue
        if 80 * K < x < 580 * K and (y < 100 * K or y > 262 * K):      # sin puntos sobre los textos ni la píldora
            continue
        r = rnd.choice((1.0, 1.4, 1.8, 2.4)) * K
        col = rnd.choice(((255, 255, 255), (255, 110, 110), (255, 170, 90)))
        dc.ellipse((x - r, y - r, x + r, y + r), fill=col + (rnd.randint(60, 150),))
    im.alpha_composite(capa.filter(ImageFilter.GaussianBlur(0.4 * K)))

    # anillo alrededor del ícono: degradado coral → rojo → naranja
    anillo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    da = ImageDraw.Draw(anillo)
    colores = [(255, 90, 95), (224, 38, 43), (255, 154, 61), (255, 90, 95)]
    pasos = 720
    for i in range(pasos):
        t = i / pasos
        seg = min(int(t * 3), 2)
        u = t * 3 - seg
        c = tuple(int(colores[seg][j] + (colores[seg + 1][j] - colores[seg][j]) * u) for j in range(3))
        a0 = -90 + 360 * t
        da.arc((CX - R, CY - R, CX + R, CY + R), a0, a0 + 360 / pasos + 0.6, fill=c + (255,), width=int(2.6 * K))
    brillo = anillo.filter(ImageFilter.GaussianBlur(6 * K))
    im.alpha_composite(brillo)
    im.alpha_composite(anillo)

    # píldora roja debajo del nombre del ícono (Finder lo escribe en negro o en blanco según el modo: se leen los dos)
    pil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pw, ph, py = 104 * K, 15 * K, 283 * K
    mascara = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((CX - pw, py - ph, CX + pw, py + ph), radius=ph, fill=255)
    grad = Image.new("RGBA", (W, H))
    gp = ImageDraw.Draw(grad)
    for x in range(CX - pw, CX + pw + 1):
        u = (x - (CX - pw)) / (2 * pw)
        gp.line((x, py - ph, x, py + ph), fill=(int(255 - 23 * u), int(98 - 46 * u), int(102 - 44 * u), 255))
    pil.paste(grad, (0, 0), mascara)
    sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((CX - pw, py - ph + 3 * K, CX + pw, py + ph + 3 * K), radius=ph,
                                             fill=(0, 0, 0, 110))
    im.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(5 * K)))
    im.alpha_composite(pil)

    d = ImageDraw.Draw(im)
    blanco, suave, tenue, coral = (246, 242, 242), (205, 192, 192), (150, 135, 135), (255, 106, 110)
    titulo = fuente("segoeuib.ttf", 34)
    centrado(d, 30 * K, "Comprobantes", titulo, blanco)
    centrado(d, 76 * K, "CINEMA PRODUCTIONS  ·  INSTALADOR PARA MAC", fuente("seguisb.ttf", 10.5), coral, espaciado=1.6)

    normal, negrita = fuente("segoeui.ttf", 15.5), fuente("segoeuib.ttf", 15.5)
    linea_mixta(d, 318 * K, [("Haz doble clic en  ", normal, blanco), ("Instalar Comprobantes", negrita, blanco),
                             ("  para instalar", normal, blanco)])
    centrado(d, 346 * K, "Se instala solo en Aplicaciones y en el Dock  ·  no necesita internet  ·  menos de 1 minuto",
             fuente("segoeui.ttf", 11.5), suave)
    centrado(d, 372 * K, "¿macOS no lo deja abrir?  Ajustes del Sistema › Privacidad y seguridad › Abrir igualmente",
             fuente("segoeui.ttf", 10), tenue)
    return im.convert("RGB")


if __name__ == "__main__":
    grande = fondo()
    grande.save(AQUI / "fondo@2x.png", dpi=(144, 144))
    grande.resize((W // K, H // K), Image.LANCZOS).save(AQUI / "fondo.png", dpi=(72, 72))
    print("fondo.png y fondo@2x.png listos en", AQUI)
