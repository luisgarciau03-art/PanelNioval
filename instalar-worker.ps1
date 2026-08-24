# Instala el worker de catalogo como Tarea Programada de Windows (OPCIONAL).
#
# La operacion normal es MANUAL: abrir iniciar-worker.bat y dejar la ventana
# abierta. Decision del owner (2026-08-24): no se quieren envios automaticos.
# Este instalador queda para quien los quiera de vuelta.
#
# Uso (PowerShell como administrador, desde la carpeta del proyecto):
#   .\instalar-worker.ps1 -IntervaloMinutos 60
#
# La tarea ejecuta iniciar-worker.bat, NO python directamente. La version
# anterior lanzaba worker_catalogo_run.py a pelo y por eso la tarea heredaba
# solo las variables persistidas con setx: sin WORKER_TOKEN ni PANEL_URL el
# heartbeat fallaba en silencio, el panel mostraba el worker como muerto, y aun
# asi el gate de envio se cumplia, o sea que enviaba catalogos sin que nadie lo
# supiera. Pasando por el .bat se hereda el mismo camino que en manual: tokens
# leidos del archivo, PANEL_URL fijado, lock por PID y limpieza de Chrome.

param(
    [int]$IntervaloMinutos = 60,
    [string]$NombreTarea = "NIOVAL_WorkerCatalogo"
)

$proyecto = $PSScriptRoot
$bat      = Join-Path $proyecto "iniciar-worker.bat"
$tokens   = Join-Path $proyecto "tokens-panelnioval.txt"

# --- Validacion previa: mejor no instalar que instalar algo roto -------------
$faltan = @()
if (-not (Test-Path $bat))    { $faltan += "iniciar-worker.bat no esta en $proyecto" }
if (-not (Test-Path $tokens)) { $faltan += "falta $tokens (WORKER_TOKEN y PANEL_DASHBOARD_TOKEN)" }

foreach ($v in 'WA_ENVIO_PASSWORD','WA_ENVIO_ARMADO') {
    $val = [Environment]::GetEnvironmentVariable($v,'User')
    if (-not $val) { $val = [Environment]::GetEnvironmentVariable($v,'Machine') }
    if (-not $val) { $faltan += "falta la variable persistente $v (setx $v ...)" }
}
$armado = [Environment]::GetEnvironmentVariable('WA_ENVIO_ARMADO','User')
if (-not $armado) { $armado = [Environment]::GetEnvironmentVariable('WA_ENVIO_ARMADO','Machine') }
if ($armado -and $armado.Trim() -ne '1') {
    $faltan += "WA_ENVIO_ARMADO vale '$armado'; el worker no enviara nada hasta que sea 1"
}

if ($faltan.Count -gt 0) {
    Write-Host "No se instala la tarea. Falta:" -ForegroundColor Yellow
    foreach ($f in $faltan) { Write-Host "  - $f" }
    Write-Host ""
    Write-Host "Una tarea a la que le falte algo se instala igual y falla en silencio cada"
    Write-Host "$IntervaloMinutos minutos, que es peor que no tenerla."
    exit 1
}

# WORKER_SIN_NAVEGADOR=1: desatendido no hay nadie para mirar el navegador ni
# para responder un prompt. El .bat lo respeta y falla rapido si falta el token.
$accion  = New-ScheduledTaskAction -Execute "cmd.exe" `
           -Argument "/c set WORKER_SIN_NAVEGADOR=1 && `"$bat`"" `
           -WorkingDirectory $proyecto
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos)
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
           -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $NombreTarea -Action $accion -Trigger $trigger `
    -Settings $ajustes -Description "Procesa la cola ENVIOS_CATALOGO y envia por WhatsApp Web" -Force

Write-Host "Tarea '$NombreTarea' instalada: cada $IntervaloMinutos min." -ForegroundColor Green
Write-Host ""
Write-Host "Comprobar que de verdad corre (State=Disabled no dispara aunque haya NextRunTime):"
Write-Host "  Get-ScheduledTaskInfo -TaskName $NombreTarea | Select LastRunTime, LastTaskResult"
Write-Host ""
Write-Host "Desactivar sin borrar:  Disable-ScheduledTask -TaskName $NombreTarea"
Write-Host "Quitar del todo:        Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:`$false"
