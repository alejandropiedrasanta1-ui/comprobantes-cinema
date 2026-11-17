#!/bin/bash
# Arma el instalador de Mac (mismo método que CineSlide) a partir de la app ya compilada con PyInstaller.
#   Uso: crear_instalador_mac.sh "<ruta a Comprobantes Cinema.app>" "<carpeta de salida>"
# Resultado: "<salida>/Instalar Comprobantes Cinema (Mac <tipo>) <versión>.dmg". Al abrirlo se ve una ventana con
# fondo «Doble clic para instalar» y la app «Instalar Comprobantes»; su doble clic abre la ventana NATIVA del
# instalador (Swift, mac/instalador_mac.swift): copia a Aplicaciones, fija en el Dock, abre el programa, se cierra
# y expulsa el disco.
# Necesita: Xcode o las Command Line Tools (swiftc) y dmgbuild (pip install dmgbuild; si falta se usa un .dmg simple).
set -euo pipefail
cd "$(dirname "$0")"
APP="$1"
SALIDA="$2"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
VERSION=$(cd .. && "$PY" -c "import rutas; print(rutas.VERSION)")
TIPO=$([ "$(uname -m)" = "arm64" ] && echo "Apple Silicon" || echo "Intel")
NOMBRE="Instalar Comprobantes.app"
TMP="$(mktemp -d)"
INST="$TMP/$NOMBRE"
mkdir -p "$INST/Contents/MacOS" "$INST/Contents/Resources" "$SALIDA"

# 1) La ventana del instalador: Swift, universal (Apple Silicon + Intel)
for arq in arm64 x86_64; do
  swiftc -swift-version 5 -O -parse-as-library -target "$arq-apple-macos13.0" mac/instalador_mac.swift -o "$TMP/instalar_$arq"
done
lipo -create "$TMP/instalar_arm64" "$TMP/instalar_x86_64" -output "$INST/Contents/MacOS/instalar"
chmod +x "$INST/Contents/MacOS/instalar"

# 2) Info.plist de «Instalar Comprobantes»
cat > "$INST/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Instalar Comprobantes</string>
  <key>CFBundleDisplayName</key><string>Instalar Comprobantes</string>
  <key>CFBundleIdentifier</key><string>com.cinemaproductions.comprobantes.instalador</string>
  <key>CFBundleExecutable</key><string>instalar</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.business</string>
</dict>
</plist>
PLIST
plutil -lint "$INST/Contents/Info.plist"

# 3) El programa va adentro, con el mismo ícono
ditto "$APP" "$INST/Contents/Resources/Comprobantes Cinema.app"
cp ../recursos/icono.png "$INST/Contents/Resources/icono.png"
ICONO=$(find "$APP/Contents/Resources" -maxdepth 1 -name "*.icns" | head -1)
if [ -n "$ICONO" ]; then cp "$ICONO" "$INST/Contents/Resources/AppIcon.icns"; fi

# 4) Firma local (ad hoc), necesaria en Mac con Apple Silicon
xattr -cr "$INST"
codesign --force --deep -s - "$INST"
codesign -v --deep "$INST" && echo "firma ad hoc OK" >&2

# 5) El .dmg: ventana con fondo «Doble clic para instalar»
DMG="$SALIDA/Instalar Comprobantes Cinema (Mac $TIPO) $VERSION.dmg"
VOLUMEN="Comprobantes Cinema $VERSION"
rm -f "$DMG"
if "$PY" -c "import dmgbuild" 2>/dev/null; then
  tiffutil -cathidpicheck mac/fondo.png mac/fondo@2x.png -out "$TMP/fondo.tiff" >/dev/null
  "$PY" -m dmgbuild -s mac/dmg_ajustes.py -D app="$INST" -D fondo="$TMP/fondo.tiff" \
    -D icono="$INST/Contents/Resources/AppIcon.icns" "$VOLUMEN" "$DMG" >&2
else
  echo "AVISO: falta dmgbuild (pip install dmgbuild); se crea un .dmg sin fondo" >&2
  mkdir -p "$TMP/dmg" && mv "$INST" "$TMP/dmg/"
  hdiutil create -volname "$VOLUMEN" -srcfolder "$TMP/dmg" -ov -format ULFO "$DMG" >/dev/null
fi
hdiutil verify "$DMG" >&2
rm -rf "$TMP"
echo "$DMG"
