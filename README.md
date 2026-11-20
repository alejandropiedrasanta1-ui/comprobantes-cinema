# Comprobantes · Cinema Productions

Programa de escritorio (Windows y Mac) para crear los comprobantes de pago de Cinema Productions:
llenas los datos del cliente, eliges el paquete (Esencial, Intermedio, Completo o Premium), subes la
captura de la transferencia y genera el JPG listo para WhatsApp. Lleva el historial de clientes,
saldos y abonos.

Los servicios de cada paquete se editan en la página *Paquetes* (✕ quita uno, «Agregar servicio» suma
otro), y los extras (Cabina 360, zancos, espejo mágico…) se suman a un cliente desde *Nuevo comprobante*.
El comprobante lo dibuja el propio programa (`dibujo.py`, sin PhotoCraft): fondo, íconos y medidas de cada
texto vienen de `PLANTILLAS/DISENO`, exportados una vez de la plantilla `PLANTILLAS/COMPROBANTE.psd`.
La lista de servicios se acomoda con las reglas de `lista.py`.

Si se cambia el diseño (solo en una computadora con **PhotoCraft**, que el programa ya no necesita):
`python crear_plantillas.py` rehace el PSD y `python herramientas/exportar_diseno.py` vuelve a exportar
`PLANTILLAS/DISENO`.

- Interfaz: PySide6 (Qt 6) + PySide6-Fluent-Widgets.
- Historial: SQLite local.

## Fuentes

Las fuentes del diseño (**Lemon Milk**, **GetVoIP Grotesque** y **Myriad Pro**) están en
`recursos/fuentes` y van dentro de los instaladores de Windows y de Mac: el programa las carga solo, no
hace falta instalarlas.

## Compilar

- **Mac**: GitHub Actions (`.github/workflows/mac.yml`) crea el `.dmg` en cada cambio.
  También se puede compilar en una Mac con `empaquetar/CREAR APP MAC.command`.
- **Windows**: `empaquetar/CREAR INSTALADOR WINDOWS.bat` crea el portable y el instalador.

## Probar

```
python generador.py                        # abre el programa
python generador.py --verificar            # arma la interfaz sin mostrarla
python generador.py --autoprueba INFORME   # genera un comprobante de cada paquete
python generador.py --prueba-vivo CARPETA  # escribe como un usuario y mide la vista en vivo
```
