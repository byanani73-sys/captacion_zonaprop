#!/bin/bash
set -e

# Escribir credentials.json desde variable de entorno
echo "$GOOGLE_CREDENTIALS" > credentials.json

# Usar modo Sheets (igual que GitHub Actions)
export GITHUB_ACTIONS=true

# Correr el scraper
python scrapers/scraper_diario.py

# Limpiar
rm -f credentials.json
