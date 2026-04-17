"""
scraper_diario.py — Actualización diaria de ZonaProp

Fases:
  1. Resetear es_nuevo
  2. Recorrer todas las páginas del listado y detectar cambios de precio
  3. Visitar detalles de propiedades nuevas e insertar en DB
  4. Marcar inactivas las que no aparecieron hoy
  5. Sincronizar Google Sheets (nuevos, precios, inactivos)

Uso:
  python scrapers/scraper_diario.py
  python scrapers/scraper_diario.py --max-paginas 5   # prueba limitada
  python scrapers/scraper_diario.py --sin-sheets       # omitir sync con Sheets
"""

import argparse
import asyncio
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Path: permite importar desde scrapers/ y pipeline/ como si fueran módulos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.scraper_inicial import (
    BROWSER_ARGS, CONTEXT_OPTS,
    extract_cards, fetch_detail, new_stealth_page, wait_for_cf,
    parse_price, parse_int,
)
from pipeline.mapear_barrios import resolver_barrio
from pipeline.extraer_tipo_url import parsear_slug

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_URL         = "https://www.zonaprop.com.ar/inmuebles-dueno-directo-capital-federal.html"
DB_PATH          = "data/zonaprop.db"
CREDENTIALS_PATH = "credentials.json"
SHEET_ID         = "13fWYaAwwe9qyVqfb08Qhu_zusak_uVvTQv3-1rhfwDA"
WORKSHEET_NAME   = "Hoja 1"

# Columnas que el script necesita en la DB (agrega las que falten)
COLUMNAS_REQUERIDAS = [
    ("es_nuevo",       "INTEGER DEFAULT 0"),
    ("bajo_precio",    "INTEGER DEFAULT 0"),
    ("precio_anterior","INTEGER"),
    ("activa",         "INTEGER DEFAULT 1"),
    ("tipo_operacion", "TEXT"),
    ("tipo_propiedad", "TEXT"),
    ("barrio_simple",  "TEXT"),
    ("orden_barrio",   "INTEGER"),
    ("m2_descubiertos","INTEGER"),
    ("m2_tasables",    "INTEGER"),
    ("precio_por_m2_total",   "REAL"),
    ("precio_por_m2_tasable", "REAL"),
]

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    """Agrega columnas requeridas si no existen."""
    existentes = {row[1] for row in conn.execute("PRAGMA table_info(propiedades)")}
    for nombre, tipo in COLUMNAS_REQUERIDAS:
        if nombre not in existentes:
            conn.execute(f"ALTER TABLE propiedades ADD COLUMN {nombre} {tipo}")
            print(f"  [DB] Columna agregada: {nombre}")
    conn.commit()


def get_existing_ids(conn: sqlite3.Connection) -> dict:
    """Devuelve {id_zonaprop: precio_actual} para todas las propiedades activas."""
    rows = conn.execute(
        "SELECT id_zonaprop, precio_actual FROM propiedades WHERE activa = 1 OR activa IS NULL"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


# ---------------------------------------------------------------------------
# Cálculo de m² y precios (lógica de pipeline/calcular_columnas.py)
# ---------------------------------------------------------------------------
def calcular_columnas(m2_totales, m2_cubiertos, precio_actual):
    """Devuelve (m2_desc, m2_tas, pm2_total, pm2_tasable) o Nones si datos insuficientes."""
    if m2_cubiertos is None or m2_totales is None or precio_actual is None:
        return None, None, None, None
    if m2_cubiertos > m2_totales:
        return None, None, None, None
    m2_desc = m2_totales - m2_cubiertos
    if m2_desc <= 25:
        m2_tas = m2_cubiertos + round(m2_desc * 0.5)
    else:
        m2_tas = m2_cubiertos + round(m2_desc * 0.33)
    pm2_total   = round(precio_actual / m2_totales, 2) if m2_totales > 0 else None
    pm2_tasable = round(precio_actual / m2_tas,    2) if m2_tas    > 0 else None
    return m2_desc, m2_tas, pm2_total, pm2_tasable


# ---------------------------------------------------------------------------
# Fase 1 — Resetear es_nuevo
# ---------------------------------------------------------------------------
def resetear_es_nuevo(conn: sqlite3.Connection) -> int:
    cur = conn.execute("UPDATE propiedades SET es_nuevo = 0 WHERE es_nuevo = 1")
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Fase 2 — Recorrer listado
# ---------------------------------------------------------------------------
async def recorrer_listado(pw, max_paginas=None) -> tuple[set, list, list]:
    """
    Recorre todas las páginas del listado.
    Devuelve:
      ids_vistos    — set de id_zonaprop que aparecieron hoy
      nuevos        — lista de dicts (cards sin detalle aún) para insertar
      actualizados  — lista de dicts {id, precio_nuevo, precio_anterior, bajo_precio}
    """
    conn = sqlite3.connect(DB_PATH)
    existentes = get_existing_ids(conn)
    conn.close()

    ids_vistos   = set()
    nuevos       = []
    actualizados = []

    list_browser, list_page = await new_stealth_page(pw)
    try:
        await list_page.goto(BASE_URL, wait_until="domcontentloaded")
        passed = await wait_for_cf(list_page)
        if not passed:
            print("  [!] No se pudo superar Cloudflare en el listado")
            return ids_vistos, nuevos, actualizados
        await list_page.wait_for_timeout(2000)

        page_num = 0
        total_tarjetas = 0

        while True:
            page_num += 1
            cards = await extract_cards(list_page)
            if not cards:
                print(f"  Página {page_num}: sin tarjetas → fin del listado")
                break

            for card in cards:
                id_zp = card.get("id_zonaprop")
                if not id_zp:
                    continue

                ids_vistos.add(id_zp)
                total_tarjetas += 1

                if id_zp in existentes:
                    # Propiedad ya conocida — comparar precio
                    precio_viejo = existentes[id_zp]
                    precio_nuevo = card.get("precio_actual")
                    if precio_nuevo and precio_viejo and precio_nuevo != precio_viejo:
                        actualizados.append({
                            "id":              id_zp,
                            "precio_nuevo":    precio_nuevo,
                            "precio_anterior": precio_viejo,
                            "bajo_precio":     1 if precio_nuevo < precio_viejo else 0,
                        })
                else:
                    # Nueva propiedad
                    nuevos.append(card)

            if total_tarjetas % 10 == 0 or page_num == 1:
                print(f"  Página {page_num}: {len(cards)} tarjetas | "
                      f"Nuevas: {len(nuevos)} | Cambios precio: {len(actualizados)} | "
                      f"Vistas: {len(ids_vistos)}")

            if max_paginas and page_num >= max_paginas:
                print(f"  Límite de páginas alcanzado ({max_paginas})")
                break

            next_btn = await list_page.query_selector('[data-qa="PAGING_NEXT"]')
            if not next_btn:
                print(f"  Página {page_num}: sin botón 'siguiente' → fin")
                break

            await asyncio.sleep(random.uniform(2, 4))
            await next_btn.click()
            await list_page.wait_for_load_state("domcontentloaded")
            if not await wait_for_cf(list_page):
                print("  [!] Cloudflare bloqueó la página siguiente")
                break
            await list_page.wait_for_timeout(2000)

        print(f"\n  Listado recorrido: {page_num} páginas, {total_tarjetas} tarjetas totales")

    finally:
        await list_browser.close()

    return ids_vistos, nuevos, actualizados


# ---------------------------------------------------------------------------
# Fase 3 — Procesar propiedades nuevas
# ---------------------------------------------------------------------------
async def procesar_nuevos(pw, nuevos: list, hoy: str) -> list:
    """
    Visita el detalle de cada propiedad nueva, construye el row completo y lo inserta.
    Devuelve lista de rows insertados (para sync con Sheets).
    """
    conn = sqlite3.connect(DB_PATH)
    insertados = []
    total = len(nuevos)

    for i, card in enumerate(nuevos, 1):
        id_zp = card.get("id_zonaprop")
        url   = card.get("url")
        if not id_zp or not url:
            continue

        # Extraer tipo desde URL
        tipo_op, tipo_prop = parsear_slug(url)

        # Visitar detalle
        detail = {}
        try:
            await asyncio.sleep(random.uniform(3, 7))
            detail = await fetch_detail(pw, url)
        except Exception as e:
            print(f"  [{i:>4}/{total}] [error detalle] {id_zp}: {e}")

        # Construir datos
        m2_totales  = detail.get("m2_totales")  or card.get("m2_totales")
        m2_cubiertos = detail.get("m2_cubiertos")
        precio      = card.get("precio_actual")
        m2_desc, m2_tas, pm2_tot, pm2_tas = calcular_columnas(m2_totales, m2_cubiertos, precio)
        barrio_simple, orden_barrio = resolver_barrio(card.get("barrio"))

        row = {
            "id_zonaprop":          id_zp,
            "url":                  url,
            "fecha_primera_vez":    hoy,
            "fecha_actualizacion":  hoy,
            "precio_actual":        precio,
            "moneda":               card.get("moneda"),
            "expensas":             card.get("expensas"),
            "m2_totales":           m2_totales,
            "m2_cubiertos":         m2_cubiertos,
            "m2_descubiertos":      m2_desc,
            "m2_tasables":          m2_tas,
            "precio_por_m2_total":  pm2_tot,
            "precio_por_m2_tasable":pm2_tas,
            "ambientes":            detail.get("ambientes") or card.get("ambientes"),
            "dormitorios":          detail.get("dormitorios") or card.get("dormitorios"),
            "banos":                detail.get("banos") or card.get("banos"),
            "toilettes":            detail.get("toilettes"),
            "cocheras":             detail.get("cocheras") or card.get("cocheras"),
            "antiguedad":           detail.get("antiguedad"),
            "disposicion":          detail.get("disposicion"),
            "orientacion":          detail.get("orientacion"),
            "luminosidad":          detail.get("luminosidad"),
            "direccion":            card.get("direccion"),
            "barrio":               card.get("barrio"),
            "barrio_simple":        barrio_simple,
            "orden_barrio":         orden_barrio,
            "descripcion":          card.get("descripcion"),
            "tipo_operacion":       tipo_op,
            "tipo_propiedad":       tipo_prop or detail.get("tipo_propiedad"),
            "es_nuevo":             1,
            "activa":               1,
            "bajo_precio":          0,
            "precio_anterior":      None,
        }

        try:
            conn.execute("""
                INSERT INTO propiedades (
                    id_zonaprop, url, fecha_primera_vez, fecha_actualizacion,
                    precio_actual, moneda, expensas,
                    m2_totales, m2_cubiertos, m2_descubiertos, m2_tasables,
                    precio_por_m2_total, precio_por_m2_tasable,
                    ambientes, dormitorios, banos, toilettes, cocheras,
                    antiguedad, disposicion, orientacion, luminosidad,
                    direccion, barrio, barrio_simple, orden_barrio,
                    descripcion, tipo_operacion, tipo_propiedad,
                    es_nuevo, activa, bajo_precio, precio_anterior
                ) VALUES (
                    :id_zonaprop, :url, :fecha_primera_vez, :fecha_actualizacion,
                    :precio_actual, :moneda, :expensas,
                    :m2_totales, :m2_cubiertos, :m2_descubiertos, :m2_tasables,
                    :precio_por_m2_total, :precio_por_m2_tasable,
                    :ambientes, :dormitorios, :banos, :toilettes, :cocheras,
                    :antiguedad, :disposicion, :orientacion, :luminosidad,
                    :direccion, :barrio, :barrio_simple, :orden_barrio,
                    :descripcion, :tipo_operacion, :tipo_propiedad,
                    :es_nuevo, :activa, :bajo_precio, :precio_anterior
                )
            """, row)
            conn.commit()
            insertados.append(row)
            pm2_str = f"USD {pm2_tas:,.0f}/m²" if pm2_tas else "sin m²"
            print(f"  [{i:>4}/{total}] ✓ {barrio_simple:<18} {pm2_str}  {url.split('/')[-1][:40]}")
        except sqlite3.IntegrityError:
            pass  # ya existía, race condition

    conn.close()
    return insertados


# ---------------------------------------------------------------------------
# Fase 4 — Marcar inactivas
# ---------------------------------------------------------------------------
def marcar_inactivas(ids_vistos: set, hoy: str) -> list:
    """
    Marca activa=0 en las propiedades que no aparecieron hoy.
    Devuelve lista de ids marcados.
    """
    conn = sqlite3.connect(DB_PATH)
    ids_activas = {
        row[0] for row in conn.execute(
            "SELECT id_zonaprop FROM propiedades WHERE activa = 1"
        ).fetchall()
    }
    ids_inactivas = ids_activas - ids_vistos

    if ids_inactivas:
        placeholders = ",".join("?" * len(ids_inactivas))
        conn.execute(
            f"UPDATE propiedades SET activa = 0, fecha_actualizacion = ? "
            f"WHERE id_zonaprop IN ({placeholders})",
            [hoy] + list(ids_inactivas),
        )
        conn.commit()

    conn.close()
    return list(ids_inactivas)


# ---------------------------------------------------------------------------
# Fase 4b — Actualizar precios en DB
# ---------------------------------------------------------------------------
def actualizar_precios_db(actualizados: list, hoy: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    for upd in actualizados:
        conn.execute("""
            UPDATE propiedades SET
                precio_actual    = ?,
                precio_anterior  = ?,
                bajo_precio      = ?,
                fecha_actualizacion = ?
            WHERE id_zonaprop = ?
        """, (upd["precio_nuevo"], upd["precio_anterior"],
              upd["bajo_precio"], hoy, upd["id"]))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fase 5 — Google Sheets sync
# ---------------------------------------------------------------------------
def connect_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)


def col_letter(idx: int) -> str:
    """Índice 0-based → letra(s) de columna."""
    result = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def sincronizar_sheets(insertados: list, actualizados: list, ids_inactivos: list) -> None:
    """
    Sincroniza cambios con Google Sheets de forma incremental:
    - Nuevos: agrega filas al final
    - Precios: actualiza celdas precio_actual / precio_anterior / bajo_precio
    - Inactivos: actualiza columna activa = 0
    """
    if not insertados and not actualizados and not ids_inactivos:
        print("  Nada que sincronizar con Sheets")
        return

    print("  Conectando al Sheet...")
    ws = connect_sheets()
    all_values = ws.get_all_values()

    if not all_values:
        print("  [!] Sheet vacío — omitiendo sync")
        return

    headers = all_values[0]
    h_idx   = {h: i for i, h in enumerate(headers)}  # header → col 0-based

    # Índice id → número de fila (1-based, incluyendo header)
    id_col = h_idx.get("id_zonaprop", 0)
    id_to_row = {
        row[id_col]: r_num
        for r_num, row in enumerate(all_values, 1)
        if r_num > 1 and len(row) > id_col
    }

    batch_updates = []

    # -----------------------------------------------------------------------
    # 5a — Nuevos: agregar filas al final con append_rows
    # -----------------------------------------------------------------------
    if insertados:
        nuevas_filas = []
        for row in insertados:
            fila = [("" if row.get(h) is None else row.get(h)) for h in headers]
            nuevas_filas.append(fila)

        # Expandir el sheet si no hay suficientes filas
        ultima_fila     = len(all_values)
        filas_actuales  = ws.row_count
        filas_necesarias = ultima_fila + len(nuevas_filas) + 100  # 100 de margen
        if filas_necesarias > filas_actuales:
            ws.add_rows(filas_necesarias - filas_actuales)
            print(f"  Sheet expandido a {filas_necesarias} filas")

        ws.append_rows(nuevas_filas, value_input_option="RAW")
        print(f"  ✓ {len(insertados)} filas nuevas agregadas al final")
        time.sleep(1)

    # -----------------------------------------------------------------------
    # 5b — Precios actualizados
    # -----------------------------------------------------------------------
    if actualizados and "precio_actual" in h_idx:
        precio_col      = col_letter(h_idx["precio_actual"])
        precio_ant_col  = col_letter(h_idx["precio_anterior"]) if "precio_anterior" in h_idx else None
        bajo_precio_col = col_letter(h_idx["bajo_precio"])     if "bajo_precio"     in h_idx else None

        updates_data = []
        for upd in actualizados:
            row_num = id_to_row.get(upd["id"])
            if not row_num:
                continue
            updates_data.append({
                "range": f"{precio_col}{row_num}",
                "values": [[upd["precio_nuevo"]]],
            })
            if precio_ant_col:
                updates_data.append({
                    "range": f"{precio_ant_col}{row_num}",
                    "values": [[upd["precio_anterior"]]],
                })
            if bajo_precio_col:
                updates_data.append({
                    "range": f"{bajo_precio_col}{row_num}",
                    "values": [[upd["bajo_precio"]]],
                })

        if updates_data:
            ws.batch_update(updates_data)
            bajaron = sum(1 for u in actualizados if u["bajo_precio"])
            subieron = len(actualizados) - bajaron
            print(f"  ✓ {len(actualizados)} precios actualizados "
                  f"({bajaron} bajaron, {subieron} subieron)")
            time.sleep(1)

    # -----------------------------------------------------------------------
    # 5c — Inactivos: marcar activa = 0
    # -----------------------------------------------------------------------
    if ids_inactivos and "activa" in h_idx:
        activa_col  = col_letter(h_idx["activa"])
        updates_data = []
        for id_zp in ids_inactivos:
            row_num = id_to_row.get(id_zp)
            if row_num:
                updates_data.append({
                    "range": f"{activa_col}{row_num}",
                    "values": [[0]],
                })
        if updates_data:
            ws.batch_update(updates_data)
            print(f"  ✓ {len(updates_data)} registros marcados inactivos en Sheets")
            time.sleep(1)
    elif ids_inactivos and "activa" not in h_idx:
        print(f"  [!] Columna 'activa' no existe en Sheets — corré pipeline/agregar_columna_excluida.py primero")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(max_paginas=None, sin_sheets=False):
    t0   = time.time()
    hoy  = datetime.now().strftime("%Y-%m-%d")
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'=' * 65}")
    print(f"SCRAPER DIARIO — {now}")
    print(f"{'=' * 65}")

    # Verificar DB
    conn = sqlite3.connect(DB_PATH)
    print("\n[DB] Verificando schema...")
    init_db(conn)
    total_inicial = conn.execute("SELECT COUNT(*) FROM propiedades").fetchone()[0]
    conn.close()
    print(f"     {total_inicial} propiedades en DB")

    # -----------------------------------------------------------------------
    # Fase 1 — Resetear es_nuevo
    # -----------------------------------------------------------------------
    print("\n[1/5] Reseteando es_nuevo...")
    conn = sqlite3.connect(DB_PATH)
    reseteados = resetear_es_nuevo(conn)
    conn.close()
    print(f"      {reseteados} registros reseteados")

    # -----------------------------------------------------------------------
    # Fase 2 — Recorrer listado
    # -----------------------------------------------------------------------
    print("\n[2/5] Recorriendo listado de ZonaProp...")
    async with async_playwright() as pw:
        ids_vistos, nuevos, actualizados = await recorrer_listado(pw, max_paginas)

        # -----------------------------------------------------------------------
        # Fase 3 — Procesar nuevos
        # -----------------------------------------------------------------------
        print(f"\n[3/5] Procesando {len(nuevos)} propiedades nuevas...")
        if nuevos:
            insertados = await procesar_nuevos(pw, nuevos, now)
        else:
            insertados = []
            print("      Sin propiedades nuevas")

    # -----------------------------------------------------------------------
    # Fase 4 — Actualizar precios + marcar inactivas
    # -----------------------------------------------------------------------
    print(f"\n[4/5] Actualizando precios y marcando inactivas...")

    if actualizados:
        actualizar_precios_db(actualizados, now)
        bajaron  = sum(1 for u in actualizados if u["bajo_precio"])
        subieron = len(actualizados) - bajaron
        print(f"      {len(actualizados)} precios actualizados ({bajaron} bajaron, {subieron} subieron)")
    else:
        print("      Sin cambios de precio")

    if max_paginas:
        print("      Marcado de inactivas SALTEADO (corrida parcial con --max-paginas)")
        ids_inactivos = []
    else:
        ids_inactivos = marcar_inactivas(ids_vistos, now)
        print(f"      {len(ids_inactivos)} propiedades marcadas inactivas")

    # -----------------------------------------------------------------------
    # Fase 5 — Sincronizar Google Sheets
    # -----------------------------------------------------------------------
    if not sin_sheets:
        print(f"\n[5/5] Sincronizando Google Sheets...")
        try:
            sincronizar_sheets(insertados, actualizados, ids_inactivos)
        except Exception as e:
            print(f"  [!] Error en sync Sheets: {e}")
    else:
        print("\n[5/5] Sheets omitido (--sin-sheets)")

    # -----------------------------------------------------------------------
    # Resumen final
    # -----------------------------------------------------------------------
    elapsed = time.time() - t0
    mins    = int(elapsed // 60)
    segs    = int(elapsed % 60)
    bajaron = sum(1 for u in actualizados if u["bajo_precio"])
    subieron = len(actualizados) - bajaron

    conn = sqlite3.connect(DB_PATH)
    total_final = conn.execute("SELECT COUNT(*) FROM propiedades").fetchone()[0]
    conn.close()

    print(f"\n{'=' * 65}")
    print("RESUMEN")
    print(f"{'=' * 65}")
    print(f"  Propiedades en DB:           {total_inicial} → {total_final}")
    print(f"  Páginas recorridas:          {max_paginas or 'todas'}")
    print(f"  IDs vistos hoy:              {len(ids_vistos)}")
    print(f"  Nuevos insertados:           {len(insertados)}")
    print(f"  Precios actualizados:        {len(actualizados)} ({bajaron} bajaron, {subieron} subieron)")
    print(f"  Marcados inactivos:          {len(ids_inactivos)}")
    print(f"  Tiempo total:                {mins}m {segs}s")
    print(f"{'=' * 65}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Scraper diario de ZonaProp")
    parser.add_argument(
        "--max-paginas", type=int, default=None,
        help="Límite de páginas a recorrer (útil para pruebas)",
    )
    parser.add_argument(
        "--sin-sheets", action="store_true",
        help="Omitir sincronización con Google Sheets",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        max_paginas=args.max_paginas,
        sin_sheets=args.sin_sheets,
    ))
