# ============================================================
# Instalador del Scraper de Captacion Inmobiliaria - Windows
# Abrir PowerShell como Administrador y correr este script
# ============================================================
$ErrorActionPreference = "Stop"

$REPO_URL   = "https://github.com/byanani73-sys/captacion_zonaprop.git"
$INSTALL_DIR = "$env:USERPROFILE\Documents\Scraper de captacion inmobiliaria"
$HORA        = 9
$MINUTO      = 0

Write-Host ""
Write-Host "======================================================"
Write-Host "  Instalador del Scraper de Captacion Inmobiliaria"
Write-Host "======================================================"
Write-Host ""

# ── 1. Verificar Python ───────────────────────────────────
Write-Host ">> Verificando Python..."
$python = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $v = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) { $python = $cmd; break }
    } catch {}
}
if (-not $python) {
    Write-Host "  X Python 3 no esta instalado."
    Write-Host "  Descargalo desde: https://www.python.org/downloads/"
    Write-Host "  IMPORTANTE: durante la instalacion marca 'Add Python to PATH'"
    Write-Host "  Despues cerrá y volvé a abrir PowerShell y ejecutá el script de nuevo."
    exit 1
}
Write-Host "  OK $( & $python --version 2>&1 )"

# ── 2. Verificar Git ──────────────────────────────────────
Write-Host ">> Verificando Git..."
try {
    $gv = git --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "  OK $gv"
} catch {
    Write-Host "  X Git no esta instalado."
    Write-Host "  Descargalo desde: https://git-scm.com/download/win"
    Write-Host "  Despues cerrá y volvé a abrir PowerShell y ejecutá el script de nuevo."
    exit 1
}

# ── 3. Clonar o actualizar repo ───────────────────────────
Write-Host ">> Descargando el codigo..."
if (Test-Path "$INSTALL_DIR\.git") {
    Write-Host "  -> El repo ya existe, actualizando..."
    git -C "$INSTALL_DIR" pull
} else {
    git clone $REPO_URL "$INSTALL_DIR"
}
Write-Host "  OK Codigo listo en: $INSTALL_DIR"

# ── 4. Crear venv e instalar dependencias ─────────────────
Write-Host ">> Instalando dependencias Python..."
Set-Location "$INSTALL_DIR"
& $python -m venv venv
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --quiet --upgrade pip
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --quiet -r requirements.txt
Write-Host "  OK Dependencias instaladas"

# ── 5. Instalar Playwright y Chromium ─────────────────────
Write-Host ">> Instalando Playwright y Chromium (puede tardar unos minutos)..."
& "$INSTALL_DIR\venv\Scripts\python.exe" -m playwright install chromium
Write-Host "  OK Playwright listo"

# ── 6. Verificar credentials.json ─────────────────────────
Write-Host ">> Verificando credentials.json..."
if (-not (Test-Path "$INSTALL_DIR\credentials.json")) {
    Write-Host ""
    Write-Host "  X Falta el archivo credentials.json"
    Write-Host "  Copialoen esta carpeta:"
    Write-Host "  $INSTALL_DIR\credentials.json"
    Write-Host ""
    Read-Host "  Una vez copiado, presiona Enter para continuar"
}
Write-Host "  OK credentials.json encontrado"

# ── 7. Tarea programada - scraper diario 9am ──────────────
Write-Host ">> Configurando tarea automatica diaria ($($HORA):$('{0:D2}' -f $MINUTO))..."

$PYTHON_EXE  = "$INSTALL_DIR\venv\Scripts\python.exe"
$SCRAPER_PY  = "$INSTALL_DIR\scrapers\scraper_diario.py"

Unregister-ScheduledTask -TaskName "CaptacionScraper" -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute $PYTHON_EXE -Argument "`"$SCRAPER_PY`"" -WorkingDirectory "$INSTALL_DIR"
$trigger  = New-ScheduledTaskTrigger -Daily -At "$($HORA):$('{0:D2}' -f $MINUTO)"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable
Register-ScheduledTask -TaskName "CaptacionScraper" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null

Write-Host "  OK Scraper programado para las $($HORA):$('{0:D2}' -f $MINUTO) todos los dias"

# ── 8. Servidor local - arrancar al iniciar sesion ────────
Write-Host ">> Configurando servidor local (http://localhost:8080)..."

$SRV_PY = "$INSTALL_DIR\scripts\servidor_local.py"

Unregister-ScheduledTask -TaskName "CaptacionServidor" -Confirm:$false -ErrorAction SilentlyContinue

$srvAction   = New-ScheduledTaskAction -Execute $PYTHON_EXE -Argument "`"$SRV_PY`"" -WorkingDirectory "$INSTALL_DIR"
$srvTrigger  = New-ScheduledTaskTrigger -AtLogOn
$srvSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 365) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "CaptacionServidor" -Action $srvAction -Trigger $srvTrigger -Settings $srvSettings -RunLevel Highest -Force | Out-Null

# Arrancar el servidor ahora mismo
Start-Process -FilePath $PYTHON_EXE -ArgumentList "`"$SRV_PY`"" -WorkingDirectory "$INSTALL_DIR" -WindowStyle Hidden

Write-Host "  OK Servidor local listo en http://localhost:8080"

# ── 9. Resumen ────────────────────────────────────────────
Write-Host ""
Write-Host "======================================================"
Write-Host "  Instalacion completada"
Write-Host "======================================================"
Write-Host ""
Write-Host "  El scraper va a correr automaticamente todos los dias"
Write-Host "  a las $($HORA):$('{0:D2}' -f $MINUTO), siempre que la compu este prendida."
Write-Host ""
Write-Host "  Para correr el scraper ahora (prueba):"
Write-Host "  cd '$INSTALL_DIR'"
Write-Host "  venv\Scripts\python.exe scrapers\scraper_diario.py --max-paginas 2"
Write-Host ""
Write-Host "  Para ver la UI en local: abrir http://localhost:8080 en el navegador"
Write-Host ""
