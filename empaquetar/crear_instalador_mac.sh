#!/bin/bash
# Arma el instalador de un clic para Mac a partir de la app ya compilada con PyInstaller.
#   Uso: crear_instalador_mac.sh "<ruta a Comprobantes Cinema.app>" "<carpeta de salida>"
# Resultado: "<salida>/Instalar Comprobantes Cinema (Mac <tipo>) <versión>.dmg", que contiene solo
# «Instalar Comprobantes Cinema»: doble clic → copia a Aplicaciones, agrega al Dock, abre y se cierra.
set -euo pipefail
cd "$(dirname "$0")"
APP="$1"
SALIDA="$2"
VERSION=$(cd .. && python3 -c "import rutas; print(rutas.VERSION)" 2>/dev/null || python -c "import rutas; print(rutas.VERSION)")
TIPO=$([ "$(uname -m)" = "arm64" ] && echo "Apple Silicon" || echo "Intel")
INSTALADOR="Instalar Comprobantes Cinema.app"
TMP="$(mktemp -d)"

# 1) El instalador (applet de AppleScript con barra de progreso)
osacompile -o "$TMP/$INSTALADOR" instalador_mac.applescript
# 2) El programa va adentro del instalador
cp -R "$APP" "$TMP/$INSTALADOR/Contents/Resources/"
# 3) Mismo ícono que el programa
ICONO=$(find "$APP/Contents/Resources" -maxdepth 1 -name "*.icns" | head -1)
if [ -n "$ICONO" ]; then cp "$ICONO" "$TMP/$INSTALADOR/Contents/Resources/applet.icns"; fi
# 4) Firma local (ad-hoc), necesaria en Mac con Apple Silicon después de modificar el paquete
codesign --force --deep --sign - "$TMP/$INSTALADOR"

# 5) El .dmg solo con el instalador
mkdir -p "$TMP/dmg" "$SALIDA"
mv "$TMP/$INSTALADOR" "$TMP/dmg/"
DMG="$SALIDA/Instalar Comprobantes Cinema (Mac $TIPO) $VERSION.dmg"
rm -f "$DMG"
hdiutil create -volname "Comprobantes Cinema" -srcfolder "$TMP/dmg" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$TMP"
echo "$DMG"
