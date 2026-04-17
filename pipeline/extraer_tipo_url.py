"""
Extrae tipo_operacion y tipo_propiedad del slug de la URL de cada propiedad
y los guarda en SQLite. No requiere Playwright ni acceso a internet.

El slug tiene 8 caracteres fijos:
  Posición 0-1: operación  (al=Alquiler, ve=Venta, te=Alquiler Temporario)
  Posición 2-3: "cl"       (clasificado — siempre igual)
  Posición 4-5: tipo       (ap=Depto, ph=PH, ca=Casa, ga=Cochera, ...)
  Posición 6-7: zona       (pa=CABA — siempre igual en nuestro scraper)

Uso:
  python pipeline/extraer_tipo_url.py
  python pipeline/extraer_tipo_url.py --dry-run   # solo muestra distribución, no escribe
"""

import argparse
import re
import sqlite3

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
DB_PATH = "data/zonaprop.db"

TIPO_OPERACION = {
    "al": "Alquiler",
    "ve": "Venta",
    "te": "Alquiler Temporario",
}

TIPO_PROPIEDAD = {
    "ap": "Departamento",
    "ed": "Departamento",       # edificio/departamento (mismo tipo)
    "ph": "PH",
    "qv": "PH",                 # "PH tipo casa / quinta-villa"
    "ca": "Casa",
    "ga": "Cochera",
    "tr": "Terreno",
    "oc": "Oficina",
    "lc": "Local Comercial",
    "bg": "Galpón",
    "de": "Depósito",
    "co": "Consultorio",
    "bn": "Bóveda",
    "fc": "Fondo de Comercio",
    "ht": "Hotel",
}


# ---------------------------------------------------------------------------
# Parseo del slug
# ---------------------------------------------------------------------------
def parsear_slug(url: str) -> tuple[str | None, str | None]:
    """
    Extrae (tipo_operacion, tipo_propiedad) del slug de la URL.
    Devuelve (None, None) si la URL no tiene el formato esperado.

    Ejemplo:
      'https://...//clasificado/alclappa-departamento...'
      slug = 'alclappa'
      ops  = 'al' → 'Alquiler'
      tipo = 'ap' → 'Departamento'
    """
    if not url:
        return None, None

    m = re.search(r"/clasificado/([a-z]{8})-", url)
    if not m:
        return None, None

    slug = m.group(1)
    ops_code  = slug[0:2]
    tipo_code = slug[4:6]

    ops  = TIPO_OPERACION.get(ops_code)
    tipo = TIPO_PROPIEDAD.get(tipo_code)

    return ops, tipo


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    """Agrega columnas nuevas si no existen."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(propiedades)")}

    if "tipo_operacion" not in cols:
        conn.execute("ALTER TABLE propiedades ADD COLUMN tipo_operacion TEXT")
        print("  → Columna tipo_operacion agregada")

    if "tipo_propiedad" not in cols:
        conn.execute("ALTER TABLE propiedades ADD COLUMN tipo_propiedad TEXT")
        print("  → Columna tipo_propiedad agregada")

    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)

    print("Verificando schema...")
    init_db(conn)

    rows = conn.execute(
        "SELECT id_zonaprop, url FROM propiedades WHERE url IS NOT NULL"
    ).fetchall()

    total = len(rows)
    print(f"Registros a procesar: {total}\n")

    actualizados    = 0
    sin_match       = 0
    stats_operacion = {}
    stats_tipo      = {}

    updates = []
    for id_zp, url in rows:
        ops, tipo = parsear_slug(url)

        if ops is None and tipo is None:
            sin_match += 1
            continue

        stats_operacion[ops or "?"]  = stats_operacion.get(ops or "?", 0) + 1
        stats_tipo[tipo or "?"]      = stats_tipo.get(tipo or "?", 0) + 1

        updates.append((ops, tipo, id_zp))
        actualizados += 1

    if not dry_run:
        conn.executemany(
            "UPDATE propiedades SET tipo_operacion = ?, tipo_propiedad = ? WHERE id_zonaprop = ?",
            updates,
        )
        conn.commit()
        print(f"Escritos {actualizados} registros en la DB.")
    else:
        print(f"[dry-run] Se escribirían {actualizados} registros.")

    conn.close()

    # --- Distribución ---
    print()
    print("=" * 45)
    print("TIPO DE OPERACIÓN")
    print("=" * 45)
    for k, v in sorted(stats_operacion.items(), key=lambda x: -x[1]):
        bar = "█" * (v * 30 // max(stats_operacion.values()))
        print(f"  {k:<22} {v:>5}  {bar}")

    print()
    print("=" * 45)
    print("TIPO DE PROPIEDAD")
    print("=" * 45)
    for k, v in sorted(stats_tipo.items(), key=lambda x: -x[1]):
        bar = "█" * (v * 30 // max(stats_tipo.values()))
        print(f"  {k:<22} {v:>5}  {bar}")

    if sin_match:
        print()
        print(f"  Sin match (slug no reconocido): {sin_match}")

    print()
    print(f"Total procesados: {actualizados + sin_match} / {total}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrae tipo_operacion y tipo_propiedad del slug de la URL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo muestra la distribución sin escribir en la DB",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(dry_run=args.dry_run)
