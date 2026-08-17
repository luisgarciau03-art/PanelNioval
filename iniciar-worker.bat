@echo off
REM ============================================================
REM  NIOVAL - Iniciar worker de catalogo (modo continuo)
REM  Abrelo ANTES de abrir el panel de Railway. Deja la ventana
REM  abierta: procesa la cola de envios cada 15s. Ctrl+C para salir.
REM ============================================================
cd /d "%~dp0"
title NIOVAL - Worker Catalogo (continuo)

REM Armar el envio para esta ventana y apuntar el panel (heartbeat).
set WA_ENVIO_ARMADO=1
REM WORKER_TOKEN es obligatorio: el heartbeat devuelve 401 sin el.
:pedir_worker_token
if "%WORKER_TOKEN%"=="" set /p WORKER_TOKEN=Token del worker:
if "%WORKER_TOKEN%"=="" (
    echo El token del worker es obligatorio: el heartbeat devuelve 401 sin el.
    goto pedir_worker_token
)
set PANEL_URL=https://web-production-1d453.up.railway.app
REM TRAS EL CORTE (Task 9) sustituir las dos URLs por:
REM   set PANEL_URL=https://panelnioval.duckdns.org

REM Abrir el formulario del panel en el navegador.
echo Abriendo el panel (formulario) en el navegador...
start "" "https://web-production-1d453.up.railway.app/formulario"

echo.
echo Iniciando worker de catalogo en modo CONTINUO...
echo (Deja esta ventana abierta. Ctrl+C para detener los envios.)
echo.
python worker_catalogo_run.py --loop

echo.
echo El worker se detuvo. Puedes cerrar esta ventana.
pause
