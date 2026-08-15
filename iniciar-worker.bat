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
REM Armar el envio para esta ventana.
set WA_ENVIO_ARMADO=1

echo.
echo Iniciando worker de catalogo en modo CONTINUO...
echo (Deja esta ventana abierta. Ctrl+C para detener los envios.)
echo.
python worker_catalogo_run.py --loop

echo.
echo El worker se detuvo. Puedes cerrar esta ventana.
pause
