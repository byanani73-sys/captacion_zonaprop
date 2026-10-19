#!/bin/bash
# ============================================================
# Instalador del Scraper de Captación Inmobiliaria
# Corre este script en la Mac donde querés instalar el scraper
# ============================================================
set -e

REPO_URL="https://github.com/byanani73-sys/captacion_zonaprop.git"
INSTALL_DIR="$HOME/Documents/Scraper de captacion inmobiliaria"
PLIST_NAME="com.captacion.zonaprop"
HORA=9   # 9am
MINUTO=0

echo ""
echo "======================================================"
echo "  Instalador del Scraper de Captación Inmobiliaria"
echo "======================================================"
echo ""

# ── 1. Verificar que esté instalado Python 3 ──────────────
echo "▶ Verificando Python..."
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "  ✗ Python 3 no está instalado."
    echo "  Descargalo desde: https://www.python.org/downloads/"
    echo "  Después de instalarlo, volvé a correr este script."
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
echo "  ✓ $PYTHON_VERSION"

# ── 2. Verificar que esté instalado Git ───────────────────
echo "▶ Verificando Git..."
if ! command -v git &>/dev/null; then
    echo ""
    echo "  ✗ Git no está instalado."
    echo "  Instalalo con: xcode-select --install"
    exit 1
fi
echo "  ✓ Git $(git --version | awk '{print $3}')"

# ── 3. Clonar o actualizar el repo ────────────────────────
echo "▶ Descargando el código..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  → El repo ya existe, actualizando..."
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
echo "  ✓ Código listo en: $INSTALL_DIR"

# ── 4. Crear entorno virtual e instalar dependencias ──────
echo "▶ Instalando dependencias Python..."
cd "$INSTALL_DIR"
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
echo "  ✓ Dependencias instaladas"

# ── 5. Instalar Playwright y Chromium ─────────────────────
echo "▶ Instalando Playwright y Chromium (puede tardar unos minutos)..."
venv/bin/playwright install chromium
echo "  ✓ Playwright listo"

# ── 6. Verificar que exista credentials.json ──────────────
echo "▶ Verificando credentials.json..."
if [ ! -f "$INSTALL_DIR/credentials.json" ]; then
    echo ""
    echo "  ✗ Falta el archivo credentials.json"
    echo "  Copialo en esta carpeta:"
    echo "  $INSTALL_DIR/credentials.json"
    echo ""
    echo "  (Pedíselo a Brian o copialo desde su compu)"
    echo ""
    read -p "  Una vez copiado, presioná Enter para continuar..."
fi
echo "  ✓ credentials.json encontrado"

# ── 7. Crear el launchd plist ─────────────────────────────
echo "▶ Configurando tarea automática diaria (${HORA}:$(printf '%02d' $MINUTO)am)..."

PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PYTHON_PATH="$INSTALL_DIR/venv/bin/python3"
SCRIPT_PATH="$INSTALL_DIR/scrapers/scraper_diario.py"
LOG_OUT="$HOME/Library/Logs/scraper_diario.log"
LOG_ERR="$HOME/Library/Logs/scraper_diario_error.log"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SCRIPT_PATH}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${HORA}</integer>
        <key>Minute</key>
        <integer>${MINUTO}</integer>
    </dict>

    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>

    <key>StandardOutPath</key>
    <string>${LOG_OUT}</string>

    <key>StandardErrorPath</key>
    <string>${LOG_ERR}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

# Cargar el launchd (descargar primero por si ya existía)
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "  ✓ Tarea programada para las ${HORA}:$(printf '%02d' $MINUTO)am todos los días"

# ── 8. Servidor local (UI + botón a demanda) ──────────────
echo "▶ Configurando servidor local (http://localhost:8080)..."

PLIST_SRV="$HOME/Library/LaunchAgents/com.captacion.servidor.plist"
SRV_SCRIPT="$INSTALL_DIR/scripts/servidor_local.py"
SRV_LOG_OUT="$HOME/Library/Logs/captacion_servidor.log"
SRV_LOG_ERR="$HOME/Library/Logs/captacion_servidor_error.log"

cat > "$PLIST_SRV" <<PLIST2
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.captacion.servidor</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SRV_SCRIPT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>

    <key>StandardOutPath</key>
    <string>${SRV_LOG_OUT}</string>

    <key>StandardErrorPath</key>
    <string>${SRV_LOG_ERR}</string>

    <key>KeepAlive</key>
    <true/>

    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
PLIST2

launchctl unload "$PLIST_SRV" 2>/dev/null || true
launchctl load "$PLIST_SRV"
echo "  ✓ Servidor local iniciado — abrí http://localhost:8080 en el navegador"

# ── 9. Resumen ────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  ✅ Instalación completada"
echo "======================================================"
echo ""
echo "  📅 Scraper automático: todos los días a las ${HORA}:$(printf '%02d' $MINUTO)am"
echo "  🌐 UI local:          http://localhost:8080"
echo "     (botón '↻ Actualizar' corre el scraper a demanda)"
echo ""
echo "  Logs del scraper:  ~/Library/Logs/scraper_diario.log"
echo "  Logs del servidor: ~/Library/Logs/captacion_servidor.log"
echo ""
echo "  Prueba manual:"
echo "  cd \"$INSTALL_DIR\" && venv/bin/python3 scrapers/scraper_diario.py --max-paginas 2"
echo ""
