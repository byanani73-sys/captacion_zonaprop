# Captación Inmobiliaria

Scraper diario de ZonaProp que detecta propiedades nuevas y las publica en Google Sheets.

## Contexto

Este es el proyecto **original / padre**. El proyecto hermano "Oportunidades Inmobiliarias"
(`~/Documents/Oportunidades Inmobiliarias`) es un fork que comparte la misma base técnica
pero tiene propósitos y operación distintos.

## Diferencias con Oportunidades Inmobiliarias

| | Captación (este proyecto) | Oportunidades Inmobiliarias |
|---|---|---|
| **Propósito** | Detectar propiedades nuevas cada día | Evaluar condición y potencial de inversión |
| **Usuario** | Papá de Brian | Brian |
| **UI** | Netlify (pública, con login Google) | Local (`frontend/index.html`) |
| **Scraper** | Automático 2x/día vía Render + launchd | Solo a demanda desde la UI |
| **Trigger a demanda** | Botón en UI → Netlify function → Render | Botón en UI → `server.py` local (`:8090`) |
| **Base de datos** | Google Sheets (via sync) | SQLite (`data/zonaprop.db`) + Sheets |

## Stack

- **Scraper**: Playwright + Python (headless Chromium, User-Agent Windows para evitar Cloudflare)
- **Backend**: Python, sin framework
- **Frontend**: HTML/JS estático en Netlify
- **Storage**: Google Sheets
- **Deploy cloud**: Render (scraper) + Netlify (frontend + functions)

## Comandos frecuentes

```bash
# Correr scraper manualmente
venv/bin/python3 scrapers/scraper_diario.py

# Solo contar candidatos nuevos (sin scrapear detalle)
venv/bin/python3 scrapers/buscar_candidatos.py --solo-contar

# Sincronizar Sheets manualmente
venv/bin/python3 scripts/sync_sheets.py
```

## Archivos clave

- `scrapers/scraper_diario.py` — scraper principal
- `scrapers/buscar_candidatos.py` — búsqueda de candidatos
- `frontend/index.html` — UI (deployada en Netlify)
- `scripts/instalar_mac.sh` — instalador para Mac nueva (papá)
- `netlify/functions/trigger-scraper.js` — endpoint que dispara el scraper en Render
