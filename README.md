# Comprobantes · Cinema Productions

Programa de escritorio (Windows y Mac) para crear los comprobantes de pago de Cinema Productions:
llenas los datos del cliente, eliges el paquete (Esencial, Intermedio, Completo o Premium), subes la
captura de la transferencia y genera el JPG listo para WhatsApp. Lleva el historial de clientes,
saldos y abonos.

Los servicios de cada paquete se editan en la página *Paquetes* (✕ quita uno, «Agregar servicio» suma
otro), y los extras (Cabina 360, zancos, espejo mágico…) se suman a un cliente desde *Nuevo comprobante*.
La lista se dibuja en cada comprobante (`lista.py`) sobre una sola plantilla (`PLANTILLAS/COMPROBANTE.psd`,
que se rehace con `python crear_plantillas.py`).

- Interfaz: PySide6 (Qt 6) + PySide6-Fluent-Widgets.
- Edición de las plantillas PSD: **PhotoCraft** (`photocraft-cli`), que debe estar instalado.
- Historial: SQLite local.

## Fuentes

Las fuentes del diseño (**Lemon Milk**, **GetVoIP Grotesque** y **Myriad Pro**) están en
`recursos/fuentes` y van dentro de los instaladores de Windows y de Mac: al abrir el programa, si
faltan en la computadora, se instalan solas (solo para el usuario). También se pueden instalar desde
otra carpeta en *Ajustes › Fuentes del diseño*.

## Compilar

- **Mac**: GitHub Actions (`.github/workflows/mac.yml`) crea el `.dmg` en cada cambio.
  También se puede compilar en una Mac con `empaquetar/CREAR APP MAC.command`.
- **Windows**: `empaquetar/CREAR INSTALADOR WINDOWS.bat` crea el portable y el instalador.

## Probar

```
python generador.py                        # abre el programa
python generador.py --verificar            # arma la interfaz sin mostrarla
python generador.py --autoprueba INFORME   # genera un comprobante de cada paquete
```
