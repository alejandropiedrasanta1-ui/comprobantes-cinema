# Mapa del código — Comprobantes · Cinema Productions

Generado por `herramientas/mapa_codigo.py` (se actualiza solo en cada commit). Formato: `archivo` (líneas) — para qué sirve · **Clase**:línea (método:línea, …) · función():línea.
Abre solo el tramo que necesites: Read con offset/limit, o Grep. No leas archivos grandes completos.

## (raíz)
- `.gitattributes` (11)
- `.gitignore` (19)
- `ABRIR GENERADOR.bat` (3)
- `app.py` (157) — Ventana principal (estilo Fluent de Windows 11) con menú lateral · **Ventana**:26 (__init__:27, ajustar_a_pantalla:68, resizeEvent:78, showEvent:84, _nuevo:89, _buscar:93, _generar:98, _pegar:105, revisar_entorno:115) · configurar_letra():131 · main():137
- `config_default.json` (72) — claves: photocraft_cli, carpeta_salida, plantilla_base, reserva_por_defecto, paquete_destacado, vista_en_vivo, calidad_jpg, paquetes, sustitutos_fuente, eventos
- `crear_plantillas.py` (256) — Crea las plantillas PSD de cada paquete (ESENCIAL, INTERMEDIO, COMPLETO, PREMIUM) a partir del diseño base, con la lista de servicios y los íconos de · _glifo_png():38 · _captura_ejemplo():49 · _lista():64 · _escala():91 · limpiar_xmp():106 · _quad():146 · crear():151
- `fuentes.py` (81) — Instala (solo para el usuario actual) las fuentes del diseño si PhotoCraft no las encuentra · faltantes():20 · incluidas():24 · _instalar_windows():30 · _instalar_mac():46 · _instalar_archivos():53 · _buscar():67 · instalar():73 · instalar_desde():79
- `generador.py` (144) — Comprobantes Cinema Productions — punto de entrada · _autoprueba():16 · _verificar():33 · _capturas():49
- `motor.py` (363) — Motor del generador · buscar_photocraft():25 · _fusionar():42 · cargar_config():51 · guardar_preferencia():68 · ruta_plantilla():80 · quetzales():84 · _cli():89 · _capas():117 · _localizar():133 · _fuentes_instaladas():176 · _estilos_sustitutos():188 · _ajustar_tamanos():206 · _preparar_captura():256 · _nombre_archivo():270 · generar():283
- `README.md` (30) — Comprobantes · Cinema Productions
- `registro.py` (150) — Historial de clientes y pagos (base de datos SQLite local) · **Cliente**:33 (saldo:46, estado:50) · _conexion():56 · nuevo_cliente():64 · agregar_pago():74 · corregir_reserva():80 · eliminar_cliente():99 · _fila_a_cliente():104 · clientes():116 · cliente():129 · pagos():135 · resumen():141
- `rutas.py` (51) — Ubicaciones del programa · _escribible():20 · recurso():48
- `ui_ajustes.py` (188) — Pantalla «Ajustes» · aplicar_tema():19 · **_EstadoFuentes**:23 (__init__:26, run:30) · **AjustesInterface**:38 (__init__:43, showEvent:120, _abrir_carpeta:125, cambiar_carpeta:130, guardar_reserva:138, ubicar_photocraft:143, revisar_fuentes:157, _mostrar_fuentes:167, instalar_fuentes:173, cambiar_tema:185)
- `ui_comun.py` (556) — Piezas compartidas de la interfaz · q():36 · fecha_larga():40 · faltan():44 · formatear_telefono():53 · digitos_telefono():63 · iniciales():68 · abrir():73 · copiar_imagen():78 · abrir_whatsapp():86 · aviso():96 · **Trabajo**:106 (__init__:111, run:115) · **Revision**:123 (__init__:127, run:131) · **Monto**:148 (__init__:153, _ajustar:160, resizeEvent:163, showEvent:167, changeEvent:171) · **ZonaCaptura**:176 (__init__:180, limpiar:191, marcar_error:198, paintEvent:202, mousePressEvent:217, buscar:220, pegar:226, usar:239, dragEnterEvent:251, dropEvent:255) · **Rejilla**:262 (__init__:266, agregar:281, _columnas_para:286, _acomodar:290, minimumSizeHint:303, sizeHint:307, resizeEvent:310) · **TarjetaPaquete**:315 (__init__:319, actualizar_precio:344, marcar:347, paintEvent:351) · **Avatar**:365 (__init__:368, poner:374, paintEvent:379) · **BarraPago**:394 (__init__:397, paintEvent:403) · etiqueta_estado():425 · **Kpi**:436 (__init__:439, poner:450) · etiqueta_valor():454 · **_Cabecera**:466 (mousePressEvent:469) · **Bloque**:474 (__init__:478, abrir:519, poner_estado:523, _pintar:528, paintEvent:548)
- `ui_historial.py` (490) — Pantalla «Clientes» · **DelegadoClientes**:30 (paint:34) · **HistorialInterface**:98 (__init__:101, resizeEvent:283, _columnas:295, showEvent:304, refrescar:308, _filtrar:348, _seleccion:352, _detalle:356, _pago_actual:401, _abrir_pago:405, _copiar_pago:412, _whatsapp:418, generar_abono:431, _fin:458, _listo:463, _fallo:474, eliminar:478)
- `ui_nuevo.py` (590) — Pantalla «Nuevo comprobante» — vista previa protagonista · _campo():29 · _chip():41 · **NuevoInterface**:50 (__init__:53, abrir_bloque:300, _evento:306, elegir_paquete:310, actualizar_precios:324, _estado_bloques:329, _cambio:358, poner_en_vivo:368, _cambiar_en_vivo:372, _datos:380, _render_vista:393, _vista_lista:410, _vista_fallo:423, _mostrar_plantilla:427, _imagen_actual:433, _poner_imagen:438, _ajustar_imagen:442, _alternar_zoom:457, _ver_vista:463, _acomodar:468, resizeEvent:485, showEvent:489, _botones_resultado:494, copiar:499, whatsapp:504, pegar:513, limpiar:517, generar:536, _fin:556, _listo:561, _fallo:587)
- `ui_paquetes.py` (122) — Pantalla «Paquetes» · **_Tarjeta**:13 (__init__:16, paintEvent:20) · **PaquetesInterface**:30 (__init__:33, guardar:116)

## empaquetar
- `comprobantes.spec` (57) — Receta de PyInstaller para Windows (carpeta con .exe) y Mac (.app)
- `CREAR APP MAC.command` (37) — Crea en COMPROBANTE/INSTALADOR el instalador de Mac (ventana nativa, como CineSlide) · [1/3] Preparando entorno de Python (solo la primera vez:20 · [2/3] Empaquetando la app...:27 · [3/3] Creando el instalador de un clic...:30
- `CREAR INSTALADOR WINDOWS.bat` (31) — Crea en COMPROBANTE\INSTALADOR · [1/2] Empaquetando el programa...:12 · [2/2] Creando el instalador (ventana propia, como CineS:15 · :error:27
- `crear_instalador_mac.sh` (78) — Arma el instalador de Mac (mismo método que CineSlide) a partir de la app ya compilada con PyInstaller · 1) La ventana del instalador: Swift, universal (Apple Silicon +:22 · 2) Info.plist de «Instalar Comprobantes»:29 · 3) El programa va adentro, con el mismo ícono:52 · 4) Firma local (ad hoc), necesaria en Mac con Apple Silicon:58 · 5) El .dmg: ventana con fondo «Doble clic para instalar»:63
- `LEEME.txt` (70) — COMPROBANTES CINEMA PRODUCTIONS - Cómo crear e instalar el programa
- `portable.spec` (49) — Versión PORTABLE

## herramientas
- `mapa_codigo.py` (160) — Genera MAPA_CODIGO.md · _primera_frase():23 · _python():30 · _comentario_inicial():46 · _regex():58 · describir():85 · archivos():110 · generar():119

## recursos
- `icono.svg` (33) — Ícono «Claqueta y recibo» — Comprobantes · Cinema Productions

## .github/workflows
- `mac.yml` (115) · Instalar dependencias:30 · Compilar la ventana del instalador (Swift):33 · Probar la interfaz desde el código:38 · Compilar la app:41 · Probar la app compilada:45 · Capturas de pantalla:48 · Crear el instalador (.dmg con ventana nativa, como CineSlide):52 · Probar el instalador como lo haría el usuario:64

## empaquetar/mac
- `crear_fondo_dmg.py` (132) — Dibuja el fondo de la ventana del .dmg de Mac («Doble clic para instalar»), como el de CineSlide · fuente():21 · centrado():25 · linea_mixta():38 · fondo():47
- `dmg_ajustes.py` (34) — Ajustes de dmgbuild para el .dmg de Mac (como el de CineSlide)
- `instalador_mac.swift` (536) — Contents/MacOS/instalar de "Instalar Comprobantes.app" (la app del DMG) · **Color**:15 · numeroVersion:35 · versionDe:40 · appInstalada:44 · ejecutar:52 · **Avance**:67 · evento:77 · objetivo:95 · avanzar:103 · **BotonPildora**:110 · makeBody:112 · **VistaInstalador**:130 · heroe:160 · luz:195 · emblema:202 · columna:265 · barra:298 · fila:317 · pie:355 · **VentanaSinMarco**:370 · **Instalador**:375 · applicationDidFinishLaunching:390 · applicationShouldTerminate:422 · enviar:427 · empezar:432 · tic:476 · abrirYSalir:489 · expulsarDisco:497 · empezarDemo:508 · alimentarDemo:518 · **Principal**:528 · main:529

## empaquetar/windows
- `construir_instalador.ps1` (76) — Arma el instalador de Windows (mismo método que CineSlide) · 1) versión y datos del archivo (Propiedades > Detalles):27 · 2) ícono de la ventana (256 px) a partir de recursos\icono.png:42 · 3) compilar (C# 5, .NET Framework 4):48 · 4) el programa en .zip:57 · 5) [instalador.exe][paquete.zip][posición Int64][CCPAQ001]:61
- `instalador_windows.cs` (1233) — Instalador de Windows de Comprobantes Cinema Productions, con el mismo método que el de CineSlide · **Inst**:31 · NumeroVersion:55 · VersionInstalada:69 · BuscarPhotoCraft:77 · CerrarPrograma:98 · Abrir:114 · BorrarCarpeta:126 · BorrarArchivo:143 · **Paquete**:166 · Abrir:172 · **Tramo**:203 · Flush:215 · Seek:219 · Read:227 · **Instalacion**:240 · Ejecutar:250 · Mensaje:279 · NombreFuente:350 · SinTipo:362 · FuenteInstalada:368 · CrearAcceso:424 · Desinstalar:473 · **Avance**:518 · Drenar:536 · Avanzar:583 · **Ventana**:591 · OnHandleCreated:681 · OnShown:687 · OnFormClosing:696 · OnFormClosed:702 · OnMouseDown:787 · OnMouseMove:797 · OnKeyDown:804 · Redondeado:831 · Capsula:843 · Brillo:849 · Palomita:869 · Luz:945 · Mezclar:952 · EnDegradado:958 · **Programa**:1170 · Main:1173

## Carpetas sin código (no abrir)
- `PLANTILLAS/` — los 4 PSD editables (COMPROBANTE - <PAQUETE>.psd) y su VISTA PREVIA - <PAQUETE>.jpg
- `recursos/` — icono.svg/.png/.ico/.icns y fuentes/ (no se sube: licencia)
- `DISEÑOS ORIGINALES/` — PSD originales y COTIZACIONES del estudio (fuera de git; NO leer)
- `COMPROBANTES GENERADOS/` — JPG generados (fuera de git; NO leer)
