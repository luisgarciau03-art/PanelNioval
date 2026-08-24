@echo off
REM ============================================================
REM  NIOVAL - Iniciar worker de catalogo (modo continuo)
REM  Abrelo ANTES de abrir el panel. Deja la ventana
REM  abierta: procesa la cola de envios cada 15s. Ctrl+C para salir.
REM ============================================================
cd /d "%~dp0"
title NIOVAL - Worker Catalogo (continuo)

REM Armar el envio para esta ventana y apuntar el panel (heartbeat).
set WA_ENVIO_ARMADO=1
REM Contrasena de envio: si no esta en el entorno, se pide una vez.
if "%WA_ENVIO_PASSWORD%"=="" set /p WA_ENVIO_PASSWORD=Contrasena de envio:
REM Los dos tokens se leen del archivo si existe. Copiarlos a mano fallo tres
REM veces seguidas: son dos cadenas de 64 hex casi identicas a la vista, y
REM confundirlas da el mismo "no autorizado" en el panel que en el heartbeat.
set "ARCHIVO_TOKENS=%~dp0tokens-panelnioval.txt"
REM Respaldo: ubicacion anterior, por si el archivo aun no se ha movido.
if not exist "%ARCHIVO_TOKENS%" set "ARCHIVO_TOKENS=%USERPROFILE%\tokens-panelnioval.txt"
if exist "%ARCHIVO_TOKENS%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ARCHIVO_TOKENS%") do (
        if /i "%%A"=="WORKER_TOKEN" set "WORKER_TOKEN=%%B"
        if /i "%%A"=="PANEL_DASHBOARD_TOKEN" set "PANEL_DASHBOARD_TOKEN=%%B"
    )
    echo Tokens leidos de %ARCHIVO_TOKENS%
) else (
    echo No se encontro %ARCHIVO_TOKENS%; se pediran a mano.
)

REM WORKER_TOKEN es obligatorio: el heartbeat devuelve 401 sin el.
:pedir_worker_token
if "%WORKER_TOKEN%"=="" set /p WORKER_TOKEN=Token del worker:
if "%WORKER_TOKEN%"=="" (
    echo El token del worker es obligatorio: el heartbeat devuelve 401 sin el.
    goto pedir_worker_token
)
set PANEL_URL=https://panelnioval.duckdns.org

REM Abrir el formulario del panel en el navegador.
REM Sin ?token= el navegador recibe 401 {"ok":false,"error":"no autorizado"}:
REM el gate del panel no distingue un navegador de cualquier otro cliente.
REM Basta con entrar una vez con el token; queda en la sesion del navegador.
if "%PANEL_DASHBOARD_TOKEN%"=="" set /p PANEL_DASHBOARD_TOKEN=Token del panel (Enter para abrir sin autenticar): 
if "%PANEL_DASHBOARD_TOKEN%"=="" (
    echo Abriendo el panel SIN token: veras "no autorizado" hasta que entres con el.
    start "" "%PANEL_URL%/formulario"
) else (
    echo Abriendo el panel autenticado en el navegador...
    start "" "%PANEL_URL%/formulario?token=%PANEL_DASHBOARD_TOKEN%"
)

echo.
echo Iniciando worker de catalogo en modo CONTINUO...
echo (Deja esta ventana abierta. Ctrl+C para detener los envios.)
echo.
python worker_catalogo_run.py --loop

echo.
echo El worker se detuvo. Puedes cerrar esta ventana.
pause
