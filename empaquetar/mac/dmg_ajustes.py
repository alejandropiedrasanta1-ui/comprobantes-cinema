# Ajustes de dmgbuild para el .dmg de Mac (como el de CineSlide): una ventana con fondo «Doble clic para instalar»
# y solo la app «Instalar Comprobantes» en el centro. Lo usa crear_instalador_mac.sh:
#   python -m dmgbuild -s mac/dmg_ajustes.py -D app=<.app> -D fondo=<fondo.tiff> -D icono=<.icns> "<volumen>" <salida.dmg>
import os.path

app = defines["app"]  # noqa: F821  (dmgbuild define "defines")
programa = defines.get("programa")  # noqa: F821  («.Comprobantes Cinema.app»: oculto por el punto, junto al instalador)
nombre = os.path.basename(app)
format = "ULFO"                 # lzfse: abre rápido (macOS 10.11+)
filesystem = "HFS+"
size = None
files = [app] + ([programa] if programa else [])
symlinks = {}
hide_extension = [nombre]       # "Instalar Comprobantes", sin ".app"
icon = defines.get("icono")  # noqa: F821
icon_locations = {nombre: (330, 200)}   # centro del ícono: el anillo del fondo y la píldora del nombre están ahí
if programa:   # fuera de la ventana: aunque el Finder muestre archivos ocultos, no se ve
    icon_locations[os.path.basename(programa)] = (330, 900)
background = defines["fondo"]  # noqa: F821
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 180
window_rect = ((200, 120), (660, 428))   # 400 del fondo + 28 de la barra de título
default_view = "icon-view"
show_icon_preview = False
include_icon_view_settings = "auto"
include_list_view_settings = "auto"
arrange_by = None
grid_offset = (0, 0)
grid_spacing = 100
scroll_position = (0, 0)
label_pos = "bottom"
text_size = 14
icon_size = 128
