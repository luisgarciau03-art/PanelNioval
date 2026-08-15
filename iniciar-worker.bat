@echo off
REM ============================================================
REM  NIOVAL - Iniciar worker de catalogo (modo continuo)
REM  Abrelo ANTES de abrir el panel de Railway. Deja la ventana
REM  abierta: procesa la cola de envios cada 15s. Ctrl+C para salir.
REM ============================================================
cd /d "%~dp0"
title NIOVAL - Worker Catalogo (continuo)

REM Contrasena de envio: si no esta en el entorno, se pide una vez.
if "%WA_ENVIO_PASSWORD%"=="" set /p WA_ENVIO_PASSWORD=Contrasena de envio:
REM Armar el envio para esta ventana y apuntar el panel (heartbeat).
set WA_ENVIO_ARMADO=1
set PANEL_URL=https://web-production-1d453.up.railway.app

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
