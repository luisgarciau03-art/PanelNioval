# Instala el worker de catálogo (Plan 5, transporte B) como Tarea Programada de Windows.
# Corre worker_catalogo_run.py cada N minutos en la PC del owner (sesión de WhatsApp Web).
#
# Uso (PowerShell como administrador, desde la carpeta del proyecto):
#   .\instalar-worker.ps1 -IntervaloMinutos 15
#
# Requisitos previos: variables de entorno del sistema TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
# PANEL_URL, WORKER_TOKEN (y GOOGLE_CREDENTIALS_JSON o el .json local del panel).

param(
    [int]$IntervaloMinutos = 15,
    [string]$NombreTarea = "NIOVAL_WorkerCatalogo"
)

$proyecto = $PSScriptRoot
$python = (Get-Command python).Source
$script = Join-Path $proyecto "worker_catalogo_run.py"

if (-not (Test-Path $script)) {
    Write-Error "No se encontró $script. Ejecuta este instalador desde la carpeta del proyecto."
    exit 1
}

$accion  = New-ScheduledTaskAction -Execute $python -Argument "`"$script`"" -WorkingDirectory $proyecto
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos)
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
           -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $NombreTarea -Action $accion -Trigger $trigger `
    -Settings $ajustes -Description "Procesa la cola ENVIOS_CATALOGO y envía por WhatsApp Web" -Force

Write-Host "Tarea '$NombreTarea' instalada: cada $IntervaloMinutos min."
Write-Host "Para quitarla:  Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:`$false"
