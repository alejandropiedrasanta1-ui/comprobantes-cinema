"""Historial de clientes y pagos (base de datos SQLite local)."""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime

import rutas

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clientes(
    id INTEGER PRIMARY KEY,
    festejado TEXT NOT NULL,
    telefono TEXT,
    evento TEXT,
    paquete TEXT,
    lugar TEXT,
    fecha_evento TEXT,
    total REAL NOT NULL,
    creado TEXT,
    servicios TEXT
);
CREATE TABLE IF NOT EXISTS pagos(
    id INTEGER PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    monto REAL NOT NULL,
    concepto TEXT,
    comprobante TEXT
);
"""


@dataclass
class Cliente:
    id: int
    festejado: str
    telefono: str
    evento: str
    paquete: str
    lugar: str
    fecha_evento: date
    total: float
    pagado: float
    num_pagos: int
    servicios: list = None   # lo que dice su comprobante (paquete con cambios y extras); None: los del paquete

    @property
    def saldo(self):
        return max(self.total - self.pagado, 0)

    @property
    def estado(self):
        if self.saldo <= 0:
            return "Pagado"
        return "Abonado" if self.num_pagos > 1 else "Reservado"


def _conexion():
    rutas.BASE_DATOS.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(rutas.BASE_DATOS)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    if "servicios" not in {f[1] for f in con.execute("PRAGMA table_info(clientes)")}:   # historial anterior
        con.execute("ALTER TABLE clientes ADD COLUMN servicios TEXT")
    return con


def _json(servicios):
    return json.dumps(servicios, ensure_ascii=False) if servicios else None


def nuevo_cliente(festejado, telefono, evento, paquete, lugar, fecha_evento: date, total, servicios=None):
    with closing(_conexion()) as con, con:
        cur = con.execute(
            "INSERT INTO clientes(festejado, telefono, evento, paquete, lugar, fecha_evento, total, creado,"
            " servicios) VALUES (?,?,?,?,?,?,?,?,?)",
            (festejado.strip(), telefono.strip(), evento, paquete, lugar.strip(),
             fecha_evento.isoformat(), float(total), datetime.now().isoformat(timespec="seconds"),
             _json(servicios)))
        return cur.lastrowid


def agregar_pago(cliente_id, fecha: date, monto, concepto, comprobante):
    with closing(_conexion()) as con, con:
        con.execute("INSERT INTO pagos(cliente_id, fecha, monto, concepto, comprobante) VALUES (?,?,?,?,?)",
                    (cliente_id, fecha.isoformat(), float(monto), concepto, str(comprobante)))


def corregir_reserva(cliente_id, festejado, telefono, evento, paquete, lugar, fecha_evento: date, total,
                     fecha_pago: date, monto, concepto, comprobante, servicios=None):
    """Si se vuelve a generar el comprobante recién hecho, actualiza ese cliente y su primer pago
    en vez de crear un cliente duplicado."""
    with closing(_conexion()) as con, con:
        con.execute("UPDATE clientes SET festejado=?, telefono=?, evento=?, paquete=?, lugar=?, fecha_evento=?,"
                    " total=?, servicios=? WHERE id=?",
                    (festejado.strip(), telefono.strip(), evento, paquete, lugar.strip(),
                     fecha_evento.isoformat(), float(total), _json(servicios), cliente_id))
        primero = con.execute("SELECT id FROM pagos WHERE cliente_id=? ORDER BY id LIMIT 1",
                              (cliente_id,)).fetchone()
        if primero:
            con.execute("UPDATE pagos SET fecha=?, monto=?, concepto=?, comprobante=? WHERE id=?",
                        (fecha_pago.isoformat(), float(monto), concepto, str(comprobante), primero[0]))
        else:
            con.execute("INSERT INTO pagos(cliente_id, fecha, monto, concepto, comprobante) VALUES (?,?,?,?,?)",
                        (cliente_id, fecha_pago.isoformat(), float(monto), concepto, str(comprobante)))


def eliminar_cliente(cliente_id):
    with closing(_conexion()) as con, con:
        con.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))


def _fila_a_cliente(f):
    return Cliente(f[0], f[1], f[2] or "", f[3] or "", f[4] or "", f[5] or "",
                   date.fromisoformat(f[6]), f[7], f[8] or 0, f[9] or 0, json.loads(f[10]) if f[10] else None)


_CONSULTA = """
SELECT c.id, c.festejado, c.telefono, c.evento, c.paquete, c.lugar, c.fecha_evento, c.total,
       COALESCE(SUM(p.monto), 0), COUNT(p.id), c.servicios
FROM clientes c LEFT JOIN pagos p ON p.cliente_id = c.id
"""


def clientes(busqueda=""):
    """Clientes ordenados por fecha del evento (los próximos primero)."""
    with closing(_conexion()) as con:
        filas = con.execute(_CONSULTA + " GROUP BY c.id ORDER BY c.fecha_evento").fetchall()
    lista = [_fila_a_cliente(f) for f in filas]
    b = busqueda.strip().lower()
    if b:
        lista = [c for c in lista if b in f"{c.festejado} {c.telefono} {c.paquete} {c.lugar} {c.evento}".lower()]
    hoy = date.today()
    # Primero los eventos que vienen (el más cercano arriba); después los pasados (el más reciente arriba)
    return sorted(lista, key=lambda c: (c.fecha_evento < hoy, abs((c.fecha_evento - hoy).days)))


def cliente(cliente_id):
    with closing(_conexion()) as con:
        f = con.execute(_CONSULTA + " WHERE c.id = ? GROUP BY c.id", (cliente_id,)).fetchone()
    return _fila_a_cliente(f) if f else None


def pagos(cliente_id):
    with closing(_conexion()) as con:
        return con.execute("SELECT id, fecha, monto, concepto, comprobante FROM pagos WHERE cliente_id = ?"
                           " ORDER BY fecha, id", (cliente_id,)).fetchall()


def resumen():
    lista = clientes()
    hoy = date.today()
    with closing(_conexion()) as con:
        n_pagos = con.execute("SELECT COUNT(*) FROM pagos").fetchone()[0]
    return {
        "por_cobrar": sum(c.saldo for c in lista),
        "eventos_mes": sum(1 for c in lista if (c.fecha_evento.year, c.fecha_evento.month) == (hoy.year, hoy.month)),
        "comprobantes": n_pagos,
    }
